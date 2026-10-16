package fr.trekmap.france;

import android.app.Activity;
import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.os.Bundle;
import android.graphics.Color;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.text.DateFormat;
import java.util.Date;

/** Offline start screen: renders without WebView, Internet or JavaScript. */
public class OfflineTreksActivity extends Activity {
    private int dp(int v){return Math.round(v*getResources().getDisplayMetrics().density);}
    private TextView text(String s,int size,int color){
        TextView t=new TextView(this);
        t.setText(s);t.setTextColor(color);t.setTextSize(size);
        t.setPadding(0,dp(7),0,dp(7));return t;
    }
    @Override public void onCreate(Bundle b){
        super.onCreate(b);showRoutes();
    }
    @Override protected void onResume(){
        super.onResume();
        if(getWindow()!=null && getWindow().getDecorView()!=null)showRoutes();
    }
    private void showRoutes(){
        ScrollView scroll=new ScrollView(this);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(22),dp(28),dp(22),dp(44));
        root.setBackgroundColor(Color.rgb(243,249,245));scroll.addView(root);
        TextView title=text("TrekMap · Hors connexion",25,Color.rgb(8,76,50));
        title.setTypeface(null,1);root.addView(title);
        root.addView(text("L'application reste accessible en mode avion. Voici les itinéraires que tu as préparés dans TrekMap avant de couper le réseau.",15,Color.DKGRAY));
        TextView note=text("⚠ Les cartes vectorielles des sections téléchargées fonctionnent sans Internet. Les zones non téléchargées restent vides. Conserve une carte de secours.",13,Color.rgb(126,67,17));
        root.addView(note);
        JSONArray routes=OfflineRouteStore.list(this);
        TextView section=text("Mes treks enregistrés ("+routes.length()+")",18,Color.rgb(9,88,59));
        section.setTypeface(null,1);root.addView(section);
        if(routes.length()==0){
            root.addView(text("Aucun trek enregistré pour Android. Reconnecte-toi, ouvre une fiche trek puis « Mode randonnée » et touche « Enregistrer dans l'application » avant de partir.",15,Color.rgb(129,61,32)));
        }
        for(int i=0;i<routes.length();i++){
            JSONObject route=routes.optJSONObject(i);
            if(route==null||!GpsTrackStore.isValidRoute(route))continue;
            String id=route.optString("id");
            Button button=new Button(this);
            button.setAllCaps(false);
            button.setText("🥾 "+route.optString("name","Randonnée")+"\n"+route.optString("region","")+
                " · "+route.optJSONArray("coords").length()+" points");
            button.setMinHeight(dp(76));
            root.addView(button,new LinearLayout.LayoutParams(-1,dp(90)));
            button.setOnClickListener(v->{
                Intent nav=new Intent(this,OfflineRouteActivity.class);
                nav.putExtra("route_id",id);startActivity(nav);
            });
            Button download=new Button(this);download.setAllCaps(false);
            download.setText("↓ Préparer la carte de ce trek");
            root.addView(download,new LinearLayout.LayoutParams(-1,dp(52)));
            download.setOnClickListener(v->{
                Intent nav=new Intent(this,OfflineDownloadActivity.class);
                nav.putExtra("route_id",id);startActivity(nav);
            });
        }
        Button retry=new Button(this);retry.setText("↻ Ouvrir TrekMap en ligne");
        retry.setAllCaps(false);
        root.addView(retry,new LinearLayout.LayoutParams(-1,dp(54)));
        retry.setOnClickListener(v->{
            ConnectivityManager cm=(ConnectivityManager)getSystemService(CONNECTIVITY_SERVICE);
            NetworkCapabilities caps=cm==null?null:cm.getNetworkCapabilities(cm.getActiveNetwork());
            if(caps!=null&&caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)){
                Intent site=new Intent(this,MainActivity.class);
                site.setAction("fr.trekmap.france.RELOAD_ONLINE");
                site.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
                startActivity(site);finish();
            }else {
                new android.app.AlertDialog.Builder(this).setMessage(
                    "Aucun réseau disponible. Tu peux continuer avec les treks enregistrés sur ton téléphone.")
                  .setPositiveButton("Compris",null).show();
            }
        });
        setContentView(scroll);
    }
    @Override public void onBackPressed(){
        // Never uncover the broken WebView in airplane mode.
        finishAffinity();
    }
}
