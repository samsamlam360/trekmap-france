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
    private Button previous,next,download,all,verify;
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
        all=new Button(this);all.setAllCaps(false);
        all.setText("✂ Préparer toutes les sections et assembler");
        root.addView(all,new LinearLayout.LayoutParams(-1,dp(58)));
        verify=new Button(this);verify.setAllCaps(false);
        verify.setText("✓ Vérifier le parcours complet");
        root.addView(verify,new LinearLayout.LayoutParams(-1,dp(54)));
        root.addView(label("Un lot télécharge au plus 320 tuiles et 24 Mo à la fois. La limite horaire du serveur est conservée : si elle est atteinte, reprends plus tard. Les grands treks n'ont pas de limite de durée : télécharge leurs étapes successivement, idéalement en Wi-Fi.",13));
        Button map=new Button(this);map.setText("🗺️ Ouvrir la carte hors ligne");map.setAllCaps(false);root.addView(map);
        map.setOnClickListener(v->{
            Intent i=new Intent(this,OfflineRouteActivity.class);
            i.putExtra("route_id",route.optString("id"));startActivity(i);
        });
        previous.setOnClickListener(v->{if(!working&&stage>0){stage--;refresh();}});
        next.setOnClickListener(v->{if(!working&&stage+1<OfflineTileStore.stages(route)){stage++;refresh();}});
        download.setOnClickListener(v->startDownload(false));
        all.setOnClickListener(v->startDownload(true));
        verify.setOnClickListener(v->verifyAll());
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
        all.setEnabled(!working);verify.setEnabled(!working);
        download.setText(working?"Téléchargement en cours…":
            (p.present>0?"↻ Compléter cette section":"↓ Télécharger cette section"));
    }
    private String summaryAll(){
        int present=0,required=0,ready=0,n=OfflineTileStore.stages(route);
        for(int i=0;i<n;i++){
            OfflineTileStore.Progress p=OfflineTileStore.progress(this,route,i);
            present+=p.present;required+=p.total;
            if(p.total>0&&p.present==p.total)ready++;
        }
        return ready+"/"+n+" sections complètes · "+present+"/"+required+
             " références de tuiles présentes (tuiles communes réutilisées).";
    }
    private void verifyAll(){
        if(working)return;
        state.setText("Vérification complète de toutes les sections…");
        new Thread(()->{
            String result=summaryAll();
            runOnUiThread(()->{
                if(isFinishing()||isDestroyed())return;
                state.setText(result+"\nLes sections complètes forment la carte continue du trek sans modifier le tracé original.");
            });
        },"trekmap-check-complete").start();
    }
    private void startDownload(boolean allStages){
        if(working)return;
        working=true;cancelled=new AtomicBoolean(false);refresh();
        final int target=stage;
        new Thread(()->{
            int from=allStages?0:target,to=allStages?OfflineTileStore.stages(route):target+1;
            int totalNew=0;long totalBytes=0;
            for(int index=from;index<to;index++){
                if(cancelled.get())break;
                OfflineTileStore.Progress before=OfflineTileStore.progress(this,route,index);
                if(before.total==0||before.present==before.total)continue;
                // The server has an hourly quota. Keep an ENTIRE click bounded,
                // even when several sections are being assembled.
                if(totalNew>=320||totalBytes>=24L*1024*1024)break;
                final int sec=index;long sizeBefore=OfflineTileStore.cachedSize(this);
                final int[] newTiles={0};final String[] message={""};
                OfflineTileStore.download(this,route,index,new OfflineTileStore.Reporter(){
                    @Override public boolean isCancelled(){return cancelled.get();}
                    @Override public void report(int done,int total,int downloaded,String result){
                        newTiles[0]=downloaded;message[0]=result;
                        runOnUiThread(()->{
                            if(isFinishing()||isDestroyed())return;
                            state.setText("Section "+(sec+1)+"/"+OfflineTileStore.stages(route)+
                                " · "+done+"/"+total+" tuiles\n"+result);
                            progress.setProgress(total==0?0:(int)(100L*done/total));
                        });
                    }
                },320-totalNew,24L*1024*1024-totalBytes);
                totalNew+=newTiles[0];
                totalBytes+=Math.max(0,OfflineTileStore.cachedSize(this)-sizeBefore);
                if(message[0].contains("Limite horaire")||message[0].contains("650 Mo")||
                   message[0].contains("24 Mo")||message[0].contains("Lot terminé"))break;
            }
            String summary=summaryAll();
            runOnUiThread(()->{
                if(isFinishing()||isDestroyed())return;
                working=false;refresh();
                state.setText(summary+"\n"+
                  (cancelled.get()?"Téléchargement interrompu. Reprends quand tu veux.":
                   "Lot terminé. Appuie à nouveau sur « Préparer toutes les sections » pour compléter les morceaux restants." )+
                  "\nLe parcours complet reste intact, les tuiles téléchargées sont automatiquement réunies.");
            });
        },"trekmap-offline-tiles").start();
    }
    @Override protected void onDestroy(){cancelled.set(true);super.onDestroy();}
}
