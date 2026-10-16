package fr.trekmap.france;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.graphics.Path;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.Locale;

/** Native schematic route view, independently available with airplane mode on. */
public class OfflineRouteActivity extends Activity {
    private JSONObject route;
    private RouteDiagram diagram;
    private TextView info;
    private Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable updater=new Runnable(){
        @Override public void run(){update();handler.postDelayed(this,2500);}
    };
    private int dp(int v){return Math.round(v*getResources().getDisplayMetrics().density);}
    @Override public void onCreate(Bundle b){
        super.onCreate(b);
        route=OfflineRouteStore.find(this,getIntent().getStringExtra("route_id"));
        if(route==null){finish();return;}
        ScrollView scroll=new ScrollView(this);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(16),dp(20),dp(16),dp(32));root.setBackgroundColor(Color.rgb(243,249,245));
        scroll.addView(root);
        TextView title=new TextView(this);title.setText("← "+route.optString("name","Randonnée"));
        title.setTextSize(21);title.setTextColor(Color.rgb(12,76,49));
        title.setOnClickListener(v->finish());root.addView(title);
        TextView warn=new TextView(this);
        warn.setText("Tracé GPS enregistré · sans fond cartographique. Le trait ne confirme pas qu'un passage est praticable. Vérifie toujours les chemins sur le terrain.");
        warn.setTextSize(13);warn.setTextColor(Color.rgb(119,68,21));warn.setPadding(0,dp(14),0,dp(12));root.addView(warn);
        diagram=new RouteDiagram();
        root.addView(diagram,new LinearLayout.LayoutParams(-1,dp(370)));
        info=new TextView(this);info.setTextSize(16);info.setTextColor(Color.rgb(12,73,47));
        info.setPadding(0,dp(14),0,dp(14));root.addView(info);
        Button detailed=new Button(this);detailed.setAllCaps(false);
        detailed.setText("🗺️ Afficher la vraie carte hors ligne");
        root.addView(detailed,new LinearLayout.LayoutParams(-1,dp(56)));
        detailed.setOnClickListener(v->{
            Intent i=new Intent(this,OfflineVectorMapActivity.class);
            i.putExtra("route_id",route.optString("id"));startActivity(i);
        });
        Button tiles=new Button(this);tiles.setAllCaps(false);
        tiles.setText("↓ Télécharger / compléter les sections de carte");
        root.addView(tiles,new LinearLayout.LayoutParams(-1,dp(54)));
        tiles.setOnClickListener(v->{
            Intent i=new Intent(this,OfflineDownloadActivity.class);
            i.putExtra("route_id",route.optString("id"));startActivity(i);
        });
        Button go=new Button(this);go.setAllCaps(false);go.setText("📍 Ouvrir le suivi GPS Android");
        root.addView(go,new LinearLayout.LayoutParams(-1,dp(54)));
        go.setOnClickListener(v->{
            Intent i=new Intent(this,GpsTrackActivity.class);
            i.putExtra("trekmap_route",route.toString());startActivity(i);
        });
        Button back=new Button(this);back.setText("← Mes treks hors ligne");back.setAllCaps(false);
        root.addView(back,new LinearLayout.LayoutParams(-1,dp(54)));
        back.setOnClickListener(v->finish());
        setContentView(scroll);update();
    }
    @Override protected void onResume(){super.onResume();handler.removeCallbacks(updater);handler.post(updater);}
    @Override protected void onPause(){handler.removeCallbacks(updater);super.onPause();}
    private void update(){
        if(route==null||info==null)return;
        JSONObject s=GpsTrackStore.read(this);
        JSONObject tracked=s.optJSONObject("route");
        boolean same=tracked!=null && tracked.optString("id").equals(route.optString("id"));
        double remaining=s.optDouble("remaining",-1),off=s.optDouble("offtrack",-1);
        String desc=same?"GPS : "+s.optString("status","prêt")+
            "\nParcourus : "+String.format(Locale.FRANCE,"%.2f km",s.optDouble("distance")/1000)+
            "\nRestant (estimé) : "+(remaining<0?"inconnu":String.format(Locale.FRANCE,"%.2f km",remaining/1000))+
            "\nÉcart au parcours : "+(off<0?"en attente":String.format(Locale.FRANCE,"%.0f m",off)) :
            "Ouvre le suivi natif pour enregistrer ta progression.";
        info.setText(desc);
        if(diagram!=null)diagram.invalidate();
    }
    private class RouteDiagram extends View {
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        RouteDiagram(){super(OfflineRouteActivity.this);}
        @Override protected void onDraw(Canvas c){
            super.onDraw(c);
            int w=getWidth(),h=getHeight();
            c.drawColor(Color.rgb(228,240,231));
            JSONArray pts=route.optJSONArray("coords");
            if(pts==null||pts.length()<2)return;
            double n=-90,s=90,e=-180,west=180;
            for(int i=0;i<pts.length();i++){
                JSONArray p=pts.optJSONArray(i);if(p==null)continue;
                double lat=p.optDouble(0),lon=p.optDouble(1);
                n=Math.max(n,lat);s=Math.min(s,lat);e=Math.max(e,lon);west=Math.min(west,lon);
            }
            double cos=Math.max(.15,Math.cos(Math.toRadians((n+s)/2)));
            double latSpan=Math.max(.00001,n-s),lonSpan=Math.max(.00001,(e-west)*cos);
            double scale=Math.min((w-dp(44))/lonSpan,(h-dp(50))/latSpan);
            double midLat=(n+s)/2,midLon=(e+west)/2;
            final double k=cos, midx=midLon,midy=midLat,m=scale;
            // route is [latitude,longitude]
            Path path=new Path();
            for(int i=0;i<pts.length();i++){
                JSONArray p=pts.optJSONArray(i);if(p==null)continue;
                float x=(float)(w/2.0+(p.optDouble(1)-midx)*k*m);
                float y=(float)(h/2.0-(p.optDouble(0)-midy)*m);
                if(i==0)path.moveTo(x,y);else path.lineTo(x,y);
            }
            paint.setStyle(Paint.Style.STROKE);paint.setStrokeCap(Paint.Cap.ROUND);
            paint.setStrokeJoin(Paint.Join.ROUND);paint.setStrokeWidth(dp(9));
            paint.setColor(Color.WHITE);c.drawPath(path,paint);
            paint.setStrokeWidth(dp(5));paint.setColor(Color.rgb(12,125,83));c.drawPath(path,paint);
            JSONArray first=pts.optJSONArray(0),last=pts.optJSONArray(pts.length()-1);
            if(first!=null && last!=null){
                paint.setStyle(Paint.Style.FILL);paint.setColor(Color.rgb(23,120,74));
                c.drawCircle((float)(w/2.0+(first.optDouble(1)-midx)*k*m),
                    (float)(h/2.0-(first.optDouble(0)-midy)*m),dp(6),paint);
                paint.setColor(Color.rgb(231,119,33));
                c.drawCircle((float)(w/2.0+(last.optDouble(1)-midx)*k*m),
                    (float)(h/2.0-(last.optDouble(0)-midy)*m),dp(6),paint);
            }
            JSONObject session=GpsTrackStore.read(OfflineRouteActivity.this);
            JSONObject tracked=session.optJSONObject("route");
            if(tracked!=null && route.optString("id").equals(tracked.optString("id")) &&
               session.has("lastLat") && session.has("lastLon")){
                float x=(float)(w/2.0+(session.optDouble("lastLon")-midx)*k*m);
                float y=(float)(h/2.0-(session.optDouble("lastLat")-midy)*m);
                paint.setStyle(Paint.Style.FILL);paint.setColor(Color.WHITE);
                c.drawCircle(x,y,dp(10),paint);
                paint.setColor(Color.rgb(24,102,195));c.drawCircle(x,y,dp(7),paint);
            }
            paint.setColor(Color.rgb(40,84,62));paint.setTextSize(dp(12));
            paint.setStyle(Paint.Style.FILL);
            c.drawText("● Départ (vert)  ● Arrivée (orange)  ● GPS (bleu)",dp(10),h-dp(10),paint);
        }
    }
}
