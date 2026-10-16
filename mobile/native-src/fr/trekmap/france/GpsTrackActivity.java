package fr.trekmap.france;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.location.LocationManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.graphics.Color;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONObject;
import org.json.JSONException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/** Explicit native GPS controls and GPX export. No embedded web or location uploads. */
public class GpsTrackActivity extends Activity {
    private static final int REQUEST_GPS=41, REQUEST_EXPORT=42;
    private JSONObject requestedRoute;
    private TextView title, details, state, stats;
    private Button start, pause, finish, export, nextDay, openMap, journal;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable redraw=new Runnable(){
        @Override public void run(){refresh();handler.postDelayed(this,1500);}
    };
    private int dp(float n){return (int)(n*getResources().getDisplayMetrics().density+0.5f);}
    private TextView label(String s,int size,int color){
        TextView t=new TextView(this);
        t.setText(s);t.setTextSize(size);t.setTextColor(color);t.setPadding(0,dp(8),0,dp(8));return t;
    }
    private Button button(String s,LinearLayout root) {
        Button b=new Button(this);b.setText(s);b.setAllCaps(false);
        root.addView(b,new LinearLayout.LayoutParams(-1,dp(54)));return b;
    }
    @Override public void onCreate(Bundle stateBundle){
        super.onCreate(stateBundle);
        loadRoute(getIntent());
        ScrollView scroll=new ScrollView(this);
        LinearLayout root=new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20),dp(18),dp(20),dp(32));
        root.setBackgroundColor(Color.rgb(244,249,245));
        scroll.addView(root);
        TextView back=label("← Retour à TrekMap",16,Color.rgb(15,91,63));
        back.setOnClickListener(v->finish());root.addView(back);
        title=label("Suivi GPS natif",23,Color.rgb(20,68,45));
        title.setTypeface(null,1);root.addView(title);
        details=label("",14,Color.DKGRAY);root.addView(details);
        state=label("",17,Color.rgb(13,99,66));root.addView(state);
        stats=label("",18,Color.rgb(28,55,43));root.addView(stats);
        start=button("▶ Démarrer l'enregistrement GPS",root);
        pause=button("⏸ Mettre en pause",root);
        finish=button("■ Terminer la randonnée",root);
        nextDay=button("☀ Passer au jour suivant",root);
        openMap=button("🗺️ Ouvrir la carte TrekMap hors ligne",root);
        journal=button("▤ Mon carnet GPS (sorties terminées)",root);
        export=button("↓ Exporter mon GPX",root);
        TextView notice=label("La position est enregistrée uniquement sur cet appareil. Une notification indique quand le GPS fonctionne écran verrouillé. Le suivi peut néanmoins être interrompu par Android ou l'économie d'énergie. Une carte de secours reste indispensable.",13,Color.DKGRAY);
        root.addView(notice);
        start.setOnClickListener(v->startPressed());
        pause.setOnClickListener(v->pausePressed());
        finish.setOnClickListener(v->finishPressed());
        export.setOnClickListener(v->exportPressed());
        nextDay.setOnClickListener(v->newDayPressed());
        openMap.setOnClickListener(v->{
            JSONObject r=shownRoute(GpsTrackStore.read(this));
            if(r!=null&&OfflineRouteStore.find(this,r.optString("id"))!=null){
                Intent intent=new Intent(this,OfflineVectorMapActivity.class);
                intent.putExtra("route_id",r.optString("id"));startActivity(intent);
            }else Toast.makeText(this,"Enregistre d'abord ce trek pour Android hors réseau.",Toast.LENGTH_LONG).show();
        });
        journal.setOnClickListener(v->startActivity(new Intent(this,TrackArchiveActivity.class)));
        setContentView(scroll);
        refresh();
    }
    @Override protected void onNewIntent(Intent i){
        super.onNewIntent(i);setIntent(i);loadRoute(i);refresh();
    }
    private void loadRoute(Intent i){
        try{
            String raw=i.getStringExtra("trekmap_route");
            JSONObject route=raw==null?null:new JSONObject(raw);
            if(GpsTrackStore.isValidRoute(route)) requestedRoute=route;
        }catch(JSONException ignored){}
    }
    @Override protected void onResume(){
        super.onResume();handler.removeCallbacks(redraw);handler.post(redraw);
    }
    @Override protected void onPause(){
        handler.removeCallbacks(redraw);super.onPause();
    }
    private JSONObject shownRoute(JSONObject session) {
        if(requestedRoute!=null)return requestedRoute;
        return session.optJSONObject("route");
    }
    private void refresh(){
        if(title==null)return;
        JSONObject session=GpsTrackStore.read(this);
        if("active".equals(session.optString("status")) && !GpsTrackService.running &&
           System.currentTimeMillis()-session.optLong("liveSinceEpoch",0)>8000){
            try{
                long last=session.optLong("lastFixEpoch",0);
                long since=session.optLong("liveSinceEpoch",0);
                long until=last>since?last:System.currentTimeMillis();
                session.put("elapsed",session.optLong("elapsed")+Math.max(0,until-since));
                session.put("liveSinceEpoch",0);
                session.put("status","interrupted");
                session.put("note","Le suivi a été interrompu par Android. Appuie sur Reprendre.");
                GpsTrackStore.save(this,session);
            }catch(org.json.JSONException ignored){}
        }
        JSONObject route=shownRoute(session);
        String st=session.optString("status","ready");
        String name=route==null?"Aucun trek sélectionné":route.optString("name","Randonnée");
        title.setText(name);
        details.setText("Mode natif Android · suivi écran verrouillé");
        state.setText("État : "+translate(st)+"\n"+session.optString("note","Choisis d'abord une randonnée sur la carte."));
        long elapsed=GpsTrackStore.elapsedWithLive(session);
        String deviation=session.optDouble("offtrack",-1)<0?"indisponible":
                String.format(Locale.FRANCE,"%.0f m",session.optDouble("offtrack"));
        String remaining=session.optDouble("remaining",-1)<0?"indisponible":
                String.format(Locale.FRANCE,"%.2f km",session.optDouble("remaining")/1000);
        double accuracy=session.optDouble("accuracy",-1);
        String gps=accuracy<0?"en attente":String.format(Locale.FRANCE,"%.0f m",accuracy);
        double walked=session.optDouble("distance")/1000;
        long moving=session.optLong("movingMs",0);
        double perDay=(session.optDouble("distance")-session.optDouble("dayStartDistance"))/1000;
        double speed=moving>0?session.optDouble("distance")/(moving/3600000d)/1000:0;
        stats.setText(String.format(Locale.FRANCE,
                "JOUR %d · %.2f km aujourd'hui\nParcourus : %.2f km · Restants : %s\nÉcart au tracé : %s · GPS : %s\nDurée totale : %02d:%02d · Marche : %02d:%02d\nVitesse moyenne en marche : %.1f km/h\nDénivelé estimé : +%.0f m\nPoints GPS : %d",
                session.optInt("dayIndex",1),perDay,walked,remaining,deviation,gps,
                elapsed/3600000,(elapsed/60000)%60,
                moving/3600000,(moving/60000)%60,speed,session.optDouble("ascent",0),
                session.optJSONArray("points")==null?0:session.optJSONArray("points").length()));
        boolean same=route!=null && session.optJSONObject("route")!=null &&
                route.optString("id").equals(session.optJSONObject("route").optString("id"));
        boolean active="active".equals(st),paused="paused".equals(st)||"interrupted".equals(st);
        start.setEnabled(route!=null&&!active&&!paused);
        pause.setEnabled(active || paused);
        pause.setText(active?"⏸ Pause":"▶ Reprendre");
        finish.setEnabled(active||paused);
        nextDay.setEnabled(active||paused);
        openMap.setEnabled(route!=null);
        export.setEnabled(session.optJSONArray("points")!=null &&
                session.optJSONArray("points").length()>=2);
        if((active||paused) && !same) {
            start.setEnabled(false);
            state.append("\nTermine le suivi en cours avant de changer de trek.");
        }
    }
    private String translate(String s){
        switch(s) {
            case "active":return "GPS en marche";
            case "paused":return "en pause";
            case "interrupted":return "interrompu";
            case "finished":return "terminé";
            default:return "prêt";
        }
    }
    private boolean hasLocation(){
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED ||
               checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED;
    }
    private boolean providerEnabled(){
        LocationManager lm=(LocationManager)getSystemService(LOCATION_SERVICE);
        return lm!=null && (lm.isProviderEnabled(LocationManager.GPS_PROVIDER) ||
                             lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER));
    }
    private void startPressed(){
        if(requestedRoute==null){
            Toast.makeText(this,"Ouvre d'abord un trek dans TrekMap.",Toast.LENGTH_LONG).show();return;
        }
        JSONObject old=GpsTrackStore.read(this);
        String st=old.optString("status");
        if("active".equals(st)||"paused".equals(st)||"interrupted".equals(st)){
            Toast.makeText(this,"Termine le suivi précédent avant d'en créer un nouveau.",Toast.LENGTH_LONG).show();return;
        }
        if(old.optJSONArray("points")!=null && old.optJSONArray("points").length()>0){
            new AlertDialog.Builder(this).setTitle("Remplacer la trace ?")
                .setMessage("L'ancienne trace sera supprimée de cet appareil. Exporte-la en GPX avant si tu souhaites la conserver.")
                .setNegativeButton("Annuler",null)
                .setPositiveButton("Remplacer",(d,w)->requestAndStart()).show();
        }else requestAndStart();
    }
    private void requestAndStart() {
        if(!hasLocation()){
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION},REQUEST_GPS);return;
        }
        if(!providerEnabled()){
            new AlertDialog.Builder(this).setMessage("Active la localisation du téléphone pour démarrer le GPS.")
                .setPositiveButton("Réglages",(d,w)->startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)))
                .setNegativeButton("Annuler",null).show();return;
        }
        Intent i=new Intent(this,GpsTrackService.class);
        i.setAction(GpsTrackService.START);
        i.putExtra("trekmap_route",requestedRoute.toString());
        startNativeService(i);
        if(Build.VERSION.SDK_INT>=33 &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},44);
    }
    private void startNativeService(Intent i) {
        try{
            if(Build.VERSION.SDK_INT>=26) startForegroundService(i); else startService(i);
        }catch(Exception e){
            Toast.makeText(this,"Impossible de lancer le suivi GPS : "+e.getMessage(),Toast.LENGTH_LONG).show();
        }
    }
    private void pausePressed(){
        JSONObject obj=GpsTrackStore.read(this);
        String current=obj.optString("status");
        if("active".equals(current)){
            Intent i=new Intent(this,GpsTrackService.class);i.setAction(GpsTrackService.PAUSE);
            startService(i);
        }else if("paused".equals(current)||"interrupted".equals(current)){
            if(!hasLocation()){
                requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION,
                        Manifest.permission.ACCESS_COARSE_LOCATION},43);return;
            }
            if(!providerEnabled()){
                Toast.makeText(this,"Active la localisation du téléphone.",Toast.LENGTH_LONG).show();return;
            }
            Intent i=new Intent(this,GpsTrackService.class);i.setAction(GpsTrackService.RESUME);
            startNativeService(i);
        }
        handler.postDelayed(this::refresh,300);
    }
    private void newDayPressed(){
        JSONObject s=GpsTrackStore.read(this);
        if(!"active".equals(s.optString("status"))&&!"paused".equals(s.optString("status")))return;
        new AlertDialog.Builder(this).setTitle("Commencer la journée suivante ?")
            .setMessage("Le kilométrage du jour sera remis à zéro. La trace complète et les statistiques précédentes seront conservées.")
            .setNegativeButton("Annuler",null)
            .setPositiveButton("Nouvelle journée",(d,w)->{
                Intent i=new Intent(this,GpsTrackService.class);
                i.setAction(GpsTrackService.NEXT_DAY);
                startService(i);handler.postDelayed(this::refresh,400);
            }).show();
    }
    private void finishPressed(){
        new AlertDialog.Builder(this).setTitle("Terminer le suivi ?")
            .setMessage("La trace sera conservée dans ton carnet GPS local. Tu pourras exporter son fichier GPX plus tard.")
            .setNegativeButton("Annuler",null)
            .setPositiveButton("Terminer",(d,w)->{
                Intent i=new Intent(this,GpsTrackService.class);
                i.setAction(GpsTrackService.FINISH);startService(i);
                handler.postDelayed(this::refresh,300);
            }).show();
    }
    private void exportPressed(){
        JSONObject session=GpsTrackStore.read(this);
        if(session.optJSONArray("points")==null || session.optJSONArray("points").length()<2)return;
        Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.setType("application/gpx+xml");
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.putExtra(Intent.EXTRA_TITLE,"trekmap-marche.gpx");
        startActivityForResult(intent,REQUEST_EXPORT);
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] granted){
        super.onRequestPermissionsResult(request,permissions,granted);
        if(request==REQUEST_GPS) {
            if(hasLocation()) requestAndStart();
            else Toast.makeText(this,"Autorise le GPS pour enregistrer ta randonnée.",Toast.LENGTH_LONG).show();
        }
        if(request==43){
            if(hasLocation())pausePressed();
            else Toast.makeText(this,"Localisation refusée.",Toast.LENGTH_LONG).show();
        }
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request!=REQUEST_EXPORT||result!=RESULT_OK||data==null||data.getData()==null)return;
        try(OutputStream out=getContentResolver().openOutputStream(data.getData())){
            if(out==null)throw new Exception("Fichier inaccessible");
            out.write(GpsTrackStore.toGpx(GpsTrackStore.read(this)).getBytes(StandardCharsets.UTF_8));
            Toast.makeText(this,"Trace GPX enregistrée.",Toast.LENGTH_LONG).show();
        }catch(Exception e){
            Toast.makeText(this,"Export impossible : "+e.getMessage(),Toast.LENGTH_LONG).show();
        }
    }
}
