package fr.trekmap.france;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONObject;
import java.util.concurrent.atomic.AtomicBoolean;

/** Download one 25-km stage at a time; partial jobs can be resumed safely. */
public class OfflineDownloadActivity extends Activity {
    private JSONObject route;
    private int stage=0;
    private TextView heading,details,state;
    private Button previous,next,download;
    private ProgressBar progress;
    private AtomicBoolean cancelled=new AtomicBoolean(false);
    private boolean working=false;
    private int dp(int v){return Math.round(v*getResources().getDisplayMetrics().density);}
    private TextView label(String s,int sp){
        TextView t=new TextView(this);t.setText(s);t.setTextSize(sp);t.setTextColor(Color.rgb(16,67,46));
        t.setPadding(0,dp(9),0,dp(9));return t;
    }
    @Override public void onCreate(Bundle b){
        super.onCreate(b);
        route=OfflineRouteStore.find(this,getIntent().getStringExtra("route_id"));
        if(route==null){finish();return;}
        stage=Math.max(0,Math.min(OfflineTileStore.stages(route)-1,getIntent().getIntExtra("stage",0)));
        ScrollView scroll=new ScrollView(this);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18),dp(28),dp(18),dp(44));root.setBackgroundColor(Color.rgb(243,249,245));
        scroll.addView(root);
        heading=label("Carte du trek",23);heading.setTypeface(null,1);root.addView(heading);
        root.addView(label("Vraies tuiles vectorielles : chemins, routes, forêts et cours d'eau. Fonds disponibles hors connexion lorsqu'une étape est complète.",14));
        details=label("",17);root.addView(details);
        state=label("",14);root.addView(state);
        progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setMax(100);
        root.addView(progress,new LinearLayout.LayoutParams(-1,dp(22)));
        previous=new Button(this);previous.setAllCaps(false);previous.setText("← Étape précédente");root.addView(previous);
        next=new Button(this);next.setAllCaps(false);next.setText("Étape suivante →");root.addView(next);
        download=new Button(this);download.setAllCaps(false);download.setText("↓ Télécharger ou reprendre cette étape");
        root.addView(download,new LinearLayout.LayoutParams(-1,dp(58)));
        root.addView(label("Un lot télécharge au plus 320 tuiles et 24 Mo à la fois. La limite horaire du serveur est conservée : si elle est atteinte, reprends plus tard. Les grands treks n'ont pas de limite de durée : télécharge leurs étapes successivement, idéalement en Wi-Fi.",13));
        Button map=new Button(this);map.setText("🗺️ Ouvrir la carte hors ligne");map.setAllCaps(false);root.addView(map);
        map.setOnClickListener(v->{
            Intent i=new Intent(this,OfflineRouteActivity.class);
            i.putExtra("route_id",route.optString("id"));startActivity(i);
        });
        previous.setOnClickListener(v->{if(!working&&stage>0){stage--;refresh();}});
        next.setOnClickListener(v->{if(!working&&stage+1<OfflineTileStore.stages(route)){stage++;refresh();}});
        download.setOnClickListener(v->startDownload());
        refresh();setContentView(scroll);
    }
    private void refresh(){
        if(route==null || heading==null)return;
        int stages=OfflineTileStore.stages(route);
        OfflineTileStore.Progress p=OfflineTileStore.progress(this,route,stage);
        heading.setText(route.optString("name","Randonnée"));
        details.setText("Section "+(stage+1)+"/"+stages+" · km "+(stage*25)+" à "+((stage+1)*25)+
            "\nCarte : "+p.present+"/"+p.total+" tuiles disponibles "+
            (p.total>0&&p.present==p.total?"✓ (complète)":"(incomplète)"));
        progress.setProgress(p.total==0?0:(int)(100L*p.present/p.total));
        if(!working)state.setText("Carte : "+(p.total>0&&p.present==p.total?"prête en mode avion":"à préparer ou reprendre")+
            "\nEspace occupé par les cartes : "+Math.round(OfflineTileStore.cachedSize(this)/1048576d)+" Mo");
        previous.setEnabled(!working&&stage>0);next.setEnabled(!working&&stage+1<stages);
        download.setEnabled(!working&&p.present<p.total);
        download.setText(working?"Téléchargement en cours…":
            (p.present>0?"↻ Compléter cette section":"↓ Télécharger cette section"));
    }
    private void startDownload(){
        if(working)return;
        working=true;cancelled=new AtomicBoolean(false);refresh();
        int target=stage;
        new Thread(()->{
            OfflineTileStore.download(this,route,target,new OfflineTileStore.Reporter(){
                @Override public boolean isCancelled(){return cancelled.get();}
                @Override public void report(int done,int total,int downloaded,String message){
                    runOnUiThread(()->{
                        if(isFinishing()||isDestroyed())return;
                        state.setText(done+"/"+total+" tuiles · "+downloaded+" nouvelles\n"+message);
                        progress.setProgress(total==0?0:(int)(100L*done/total));
                    });
                }
            });
            runOnUiThread(()->{
                if(isFinishing()||isDestroyed())return;
                String status=state.getText().toString();
                working=false;refresh();
                state.setText(status+"\n"+details.getText());
            });
        },"trekmap-offline-tiles").start();
    }
    @Override protected void onDestroy(){cancelled.set(true);super.onDestroy();}
}
