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
    private static final String CHANNEL="trekmap_gps_recording";
    private static final int NOTIFICATION_ID=4205;
    private LocationManager manager;
    private Location previous;
    private long lastSampleTime,activeSince;
    private JSONObject session;

    @Override public void onCreate(){
        super.onCreate();
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
        return b.setSmallIcon(android.R.drawable.ic_menu_mylocation)
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
            set("note","Randonnée terminée. Exporte ton GPX.");
            GpsTrackStore.save(this,session);
            stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();
            return START_NOT_STICKY;
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
            GpsTrackStore.save(this,session);
            activeSince=SystemClock.elapsedRealtime();
            previous=null;lastSampleTime=0;startGps();
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
        if(location.hasAccuracy() && location.getAccuracy()>45){
            set("accuracy",Math.round(location.getAccuracy()));
            set("note","Signal GPS trop imprécis.");GpsTrackStore.save(this,session);return;
        }
        // Reject teleport jumps without resetting the accepted anchor.
        double step=previous==null?0:location.distanceTo(previous);
        double seconds=previous==null?10:Math.max(1,(SystemClock.elapsedRealtime()-lastSampleTime)/1000d);
        if(previous!=null && step/seconds>4.4){
            set("note","Saut GPS ignoré.");
            GpsTrackStore.save(this,session);return;
        }
        GpsTrackStore.appendLocation(session,location,previous,lastSampleTime);
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
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent){return null;}
}
