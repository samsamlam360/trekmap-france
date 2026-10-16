package fr.trekmap.france;
import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.widget.ScrollView;
import android.widget.LinearLayout;
import android.widget.Button;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.Locale;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.text.DateFormat;
import java.util.Date;
/** Local hiking journal: saved GPX survives subsequent recordings and network loss. */
public class TrackArchiveActivity extends Activity {
    private long chosenDate=0;
    private int dp(int x){return Math.round(x*getResources().getDisplayMetrics().density);}
    @Override public void onCreate(Bundle b){super.onCreate(b);refresh();}
    private void refresh(){
        ScrollView scroll=new ScrollView(this);
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(16),dp(24),dp(16),dp(30));root.setBackgroundColor(Color.rgb(244,249,245));
        scroll.addView(root);
        TextView title=new TextView(this);title.setText("← Carnet de randonnée");title.setTextSize(25);
        title.setTextColor(Color.rgb(13,85,57));root.addView(title);title.setOnClickListener(v->finish());
        TextView note=new TextView(this);
        note.setText("Tes traces et leurs fichiers GPX restent sur cet appareil. Aucun partage automatique ni envoi sur un serveur.");
        note.setTextSize(14);note.setPadding(0,dp(10),0,dp(14));root.addView(note);
        JSONArray list=TrackArchive.list(this);
        if(list.length()==0){
            TextView empty=new TextView(this);empty.setText("Aucune randonnée terminée. Enregistre et termine un suivi GPS pour retrouver ici sa trace.");
            empty.setTextSize(16);root.addView(empty);
        }
        for(int i=0;i<list.length();i++){
            JSONObject item=list.optJSONObject(i);if(item==null)continue;
            long date=item.optLong("date");
            String name=item.optString("name","Randonnée");
            TextView info=new TextView(this);
            info.setText(name+"\n"+DateFormat.getDateInstance(DateFormat.MEDIUM,Locale.FRANCE).format(new Date(date))+
                " · "+String.format(Locale.FRANCE,"%.2f km",item.optDouble("distance")/1000)+
                " · "+item.optInt("days",1)+" jour(s) · +"+Math.round(item.optDouble("ascent"))+" m");
            info.setTextColor(Color.rgb(15,69,47));info.setTextSize(16);
            info.setPadding(dp(10),dp(16),dp(10),dp(10));root.addView(info);
            Button export=new Button(this);export.setAllCaps(false);export.setText("↓ Exporter le GPX");
            root.addView(export,new LinearLayout.LayoutParams(-1,dp(52)));
            export.setOnClickListener(v->{
                chosenDate=date;
                Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("application/gpx+xml");
                intent.putExtra(Intent.EXTRA_TITLE,"trekmap-"+date+".gpx");
                startActivityForResult(intent,80);
            });
            String id=item.optString("routeId");
            if(OfflineRouteStore.find(this,id)!=null){
                Button map=new Button(this);map.setText("🗺️ Voir ce trek sur ma carte");
                map.setAllCaps(false);root.addView(map);
                map.setOnClickListener(v->{
                    Intent intent=new Intent(this,OfflineVectorMapActivity.class);
                    intent.putExtra("route_id",id);startActivity(intent);
                });
            }
        }
        setContentView(scroll);
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request!=80||result!=RESULT_OK||data==null||data.getData()==null||chosenDate<=0)return;
        File src=TrackArchive.file(this,chosenDate);
        try(InputStream in=new FileInputStream(src);
            OutputStream out=getContentResolver().openOutputStream(data.getData())){
            if(out==null)throw new Exception("Destination GPX inaccessible");
            byte[] block=new byte[16384];int n;
            while((n=in.read(block))>=0)out.write(block,0,n);
            android.widget.Toast.makeText(this,"Trace GPX exportée",android.widget.Toast.LENGTH_SHORT).show();
        }catch(Exception e){android.widget.Toast.makeText(this,"Export impossible : "+e.getMessage(),android.widget.Toast.LENGTH_LONG).show();}
    }
}
