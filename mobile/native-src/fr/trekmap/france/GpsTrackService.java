package fr.trekmap.france;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.IBinder;
import android.os.SystemClock;
import android.util.Log;
import org.json.JSONObject;
import org.json.JSONException;

/**
 * Native location Foreground Service: stays active when WebView sleeps/phone locks.
 * Starts ONLY from explicit Activity button and foreground runtime permission.
 * Never uses Internet or sends GPS data to TrekMap/Render/Neon.
 */
public class GpsTrackService extends Service implements LocationListener {
    static final String START="fr.trekmap.france.START";
    static final String PAUSE="fr.trekmap.france.PAUSE";
    static final String RESUME="fr.trekmap.france.RESUME";
    static final String FINISH="fr.trekmap.france.FINISH";
    static final String NEXT_DAY="fr.trekmap.france.NEXT_DAY";
    static volatile boolean running=false;
    private static final String CHANNEL="trekmap_gps_recording";
    private static final int NOTIFICATION_ID=4205;
    private LocationManager manager;
    private Location previous;
    private long lastSampleTime,activeSince;
    private JSONObject session;

    @Override public void onCreate(){
        super.onCreate();
        running=true;
        manager=(LocationManager)getSystemService(LOCATION_SERVICE);
        session=GpsTrackStore.read(this);
        if(Build.VERSION.SDK_INT>=26){
            NotificationChannel ch=new NotificationChannel(CHANNEL,"Suivi de randonnée",
                    NotificationManager.IMPORTANCE_LOW);
            ch.setDescription("Suivi GPS actif pendant la marche, même écran verrouillé");
            getSystemService(NotificationManager.class).createNotificationChannel(ch);
        }
    }
    private Notification notification(String line) {
        Intent to=new Intent(this,GpsTrackActivity.class);
        to.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
        int flags=PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE;
        PendingIntent pi=PendingIntent.getActivity(this,0,to,flags);
        Notification.Builder b=Build.VERSION.SDK_INT>=26
                ?new Notification.Builder(this,CHANNEL):new Notification.Builder(this);
        Intent pauseIntent=new Intent(this,GpsTrackService.class);
        pauseIntent.setAction("active".equals(session==null?"":session.optString("status"))?PAUSE:RESUME);
        PendingIntent toggle=PendingIntent.getService(this,1,pauseIntent,flags);
        return b.addAction(android.R.drawable.ic_media_pause,
                "active".equals(session==null?"":session.optString("status"))?"Pause":"Reprendre",
                toggle)
                .setSmallIcon(android.R.drawable.ic_menu_mylocation)
                .setContentTitle("TrekMap · GPS natif")
                .setContentText(line)
                .setContentIntent(pi).setOngoing(true).setOnlyAlertOnce(true)
                .build();
    }
    private void foreground(String line) {
        Notification n=notification(line);
        if(Build.VERSION.SDK_INT>=29)
            startForeground(NOTIFICATION_ID,n,ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
        else startForeground(NOTIFICATION_ID,n);
    }
    private boolean permissionOk() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED ||
               checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED;
    }
    @Override public int onStartCommand(Intent intent,int flags,int startId) {
        if(intent==null){stopSelf();return START_NOT_STICKY;}
        String cmd=intent.getAction();
        if(FINISH.equals(cmd)){
            stopGps();
            clockStop();
            set("status","finished");
            set("liveSinceEpoch",0);
            set("note","Randonnée terminée. Trace conservée dans le carnet local.");
            GpsTrackStore.save(this,session);
            TrackArchive.add(this,session);
            stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();
            return START_NOT_STICKY;
        }
        if(NEXT_DAY.equals(cmd)){
            session=GpsTrackStore.read(this);
            String status=session.optString("status");
            if("active".equals(status)||"paused".equals(status)){
                try{GpsTrackStore.nextDay(session);}
                catch(JSONException e){Log.e("TrekMapGPS","Cannot advance day",e);}
                set("note","Nouvelle journée démarrée, suivi précédent conservé.");
                GpsTrackStore.save(this,session);
                foreground("Journée "+session.optInt("dayIndex",1)+" · "+status);
            }
            return START_STICKY;
        }
        if(!permissionOk()) {stopSelf();return START_NOT_STICKY;}
        if(START.equals(cmd)) {
            try{
                JSONObject route=new JSONObject(intent.getStringExtra("trekmap_route"));
                if(!GpsTrackStore.isValidRoute(route)){stopSelf();return START_NOT_STICKY;}
                session=GpsTrackStore.initial(route);
            }catch(Exception e){Log.e("TrekMapGPS","Invalid route",e);stopSelf();return START_NOT_STICKY;}
        }else if(RESUME.equals(cmd)) {
            session=GpsTrackStore.read(this);
            if(!"paused".equals(session.optString("status")) &&
               !"interrupted".equals(session.optString("status"))) {
                stopSelf();return START_NOT_STICKY;
            }
        }else if(PAUSE.equals(cmd)) {
            session=GpsTrackStore.read(this);
            if(!"active".equals(session.optString("status")))return START_NOT_STICKY;
            stopGps();clockStop();set("status","paused");
            set("note","Randonnée en pause.");
            GpsTrackStore.save(this,session);
            foreground("Suivi en pause · Appuie pour reprendre");
            return START_STICKY;
        }else {stopSelf();return START_NOT_STICKY;}
        // Call startForeground immediately after Context.startForegroundService.
        try {
            foreground("Suivi en cours · Appuie pour ouvrir");
            set("status","active");
            set("note","Recherche du signal GPS…");
            set("liveSinceEpoch",System.currentTimeMillis());
            GpsTrackStore.save(this,session);
            // Refresh the action now that status has changed to "active".
            getSystemService(NotificationManager.class).notify(NOTIFICATION_ID,
                    notification("Suivi actif · Pause disponible dans la notification"));
            activeSince=SystemClock.elapsedRealtime();
            previous=null;lastSampleTime=0;
            // The three-departure counter is meaningful only for consecutive
            // fixes within one uninterrupted GPS recording window.
            set("offtrackFixes",0);
            startGps();
        }catch(Exception e){
            Log.e("TrekMapGPS","Unable to start location service",e);
            set("status","interrupted");set("note","Service GPS indisponible : permissions ou localisation.");
            GpsTrackStore.save(this,session);
            stopGps();stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();
        }
        return START_NOT_STICKY;
    }
    private void startGps(){
        if(manager==null)throw new IllegalStateException("No LocationManager");
        if(!permissionOk())throw new SecurityException("Location denied");
        if(manager.isProviderEnabled(LocationManager.GPS_PROVIDER)){
            manager.requestLocationUpdates(LocationManager.GPS_PROVIDER,3000L,5f,this);
        } else if(manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)){
            manager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER,5000L,10f,this);
            set("note","GPS satellite indisponible : précision réseau limitée.");
        } else throw new IllegalStateException("Location disabled");
    }
    private void stopGps() {
        if(manager!=null)try{manager.removeUpdates(this);}catch(SecurityException ignored){}
        previous=null;lastSampleTime=0;
    }
    private void clockStop() {
        if(activeSince>0) {
            set("elapsed",session.optLong("elapsed")+Math.max(0,SystemClock.elapsedRealtime()-activeSince));
            set("liveSinceEpoch",0);
            activeSince=0;
        }
    }
    private void set(String k,Object val){
        try{session.put(k,val);}catch(JSONException e){Log.e("TrekMapGPS","Session JSON",e);}
    }
    @Override public void onLocationChanged(Location location){
        if(!"active".equals(session.optString("status")))return;
        if(location.isFromMockProvider()) {
            set("note","Position simulée ignorée.");GpsTrackStore.save(this,session);return;
        }
        if(location.getTime()<System.currentTimeMillis()-30000)return;
        // A missing accuracy estimate is never permission to count metres.
        if(!location.hasAccuracy() || !Float.isFinite(location.getAccuracy()) ||
                location.getAccuracy()>45 || location.getAccuracy()<0){
            set("accuracy",location.hasAccuracy() && Float.isFinite(location.getAccuracy())
                    ?Math.round(location.getAccuracy()):-1);
            set("note","Position GPS sans précision fiable. Distance non comptée.");
            GpsTrackStore.save(this,session);return;
        }
        // Android may deliver cached fixes out of order after the screen wakes.
        // Monotonic fix timestamps stop an older position counting as a walk.
        if(previous!=null &&
                location.getElapsedRealtimeNanos()<=previous.getElapsedRealtimeNanos()){
            return;
        }
        // A long location outage must not become a fictitious straight-line
        // walk. Reacquire an anchor and count only subsequent measured legs.
        boolean gpsRecovered=false;
        if(previous!=null &&
                location.getElapsedRealtimeNanos()-previous.getElapsedRealtimeNanos()>90000000000L){
            previous=null;lastSampleTime=0;gpsRecovered=true;
            set("offtrackFixes",0);  // Departure confirmations cannot span a GPS outage.
        }
        // Reject teleport jumps without resetting the accepted anchor.
        double step=previous==null?0:location.distanceTo(previous);
        double seconds=previous==null?10:Math.max(1,(SystemClock.elapsedRealtime()-lastSampleTime)/1000d);
        if(previous!=null && step/seconds>4.4){
            set("note","Saut GPS ignoré.");
            GpsTrackStore.save(this,session);return;
        }
        int before=session.optInt("offtrackFixes",0);
        GpsTrackStore.appendLocation(session,location,previous,lastSampleTime);
        if(gpsRecovered)set("note","GPS retrouvé après une coupure : distance sans signal non calculée.");
        // Haptic departure alert only after 3 consecutive accurate fixes,
        // never more than once every 3 minutes.
        if(before<3 && session.optInt("offtrackFixes",0)>=3 &&
            System.currentTimeMillis()-session.optLong("lastWarningEpoch",0)>180000) {
            set("lastWarningEpoch",System.currentTimeMillis());
            android.os.Vibrator vib=(android.os.Vibrator)getSystemService(VIBRATOR_SERVICE);
            if(vib!=null && vib.hasVibrator()){
                try{
                    if(Build.VERSION.SDK_INT>=26)
                        vib.vibrate(android.os.VibrationEffect.createWaveform(new long[]{0,170,150,170},-1));
                    else vib.vibrate(350);
                }catch(SecurityException e){Log.w("TrekMapGPS","Vibration unavailable",e);}
            }
        }
        boolean accepted=previous==null || step>=Math.max(6,Math.max(
                location.hasAccuracy()?location.getAccuracy():45,
                previous.getAccuracy())*0.65);
        if(accepted){previous=new Location(location);lastSampleTime=SystemClock.elapsedRealtime();}
        GpsTrackStore.save(this,session);
    }
    @Override public void onDestroy() {
        stopGps();
        if(session!=null && "active".equals(session.optString("status"))) {
            clockStop();set("status","interrupted");
            set("note","Suivi interrompu par Android. Reprends manuellement.");
            GpsTrackStore.save(this,session);
        }
        running=false;
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent){return null;}
}
