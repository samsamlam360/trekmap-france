package fr.trekmap.france;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.graphics.Color;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Button;
import android.widget.ScrollView;
import androidx.core.content.FileProvider;
import java.io.File;

/** User-controlled installation: non-Play apps cannot silently replace themselves. */
public class TrekMapUpdateActivity extends Activity {
    private TextView status;
    private Button action;
    private TrekMapUpdateManager.Release release;
    private File downloaded;
    private final Handler handler=new Handler(Looper.getMainLooper());

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        ScrollView scroll=new ScrollView(this);
        LinearLayout view=new LinearLayout(this);
        view.setOrientation(LinearLayout.VERTICAL);
        int padding=(int)(24*getResources().getDisplayMetrics().density);
        view.setPadding(padding,padding,padding,padding);
        view.setBackgroundColor(Color.rgb(242,249,244));
        scroll.addView(view);
        TextView title=new TextView(this);
        title.setText("Mise à jour TrekMap France");title.setTextColor(Color.rgb(9,73,49));
        title.setTextSize(23);view.addView(title);
        status=new TextView(this);
        status.setTextSize(16);
        status.setPadding(0,padding,0,padding);
        status.setText("Vérification de la dernière version signée…");
        view.addView(status);
        action=new Button(this);
        action.setAllCaps(false);action.setText("Vérification...");
        action.setEnabled(false);view.addView(action);
        TextView note=new TextView(this);
        note.setText("Les mises à jour officielles proviennent du dépôt GitHub TrekMap France. Android demandera ton autorisation avant toute installation. Ne désinstalle pas l'application : tu conserveras alors tes traces GPS locales.");
        note.setTextSize(13);view.addView(note);
        setContentView(scroll);
        check();
    }
    private void display(String message){handler.post(()->status.setText(message));}
    private void check(){
        new Thread(()->{
            try{
                TrekMapUpdateManager.Release r=TrekMapUpdateManager.latest();
                long current=TrekMapUpdateManager.installedVersion(this);
                handler.post(()->{
                    if(isFinishing()||isDestroyed())return;
                    if(r==null){status.setText("Aucune version signée disponible pour l'instant.");return;}
                    if(r.version<=current){status.setText("TrekMap est à jour (version "+current+").");return;}
                    release=r;
                    status.setText("Nouvelle version : "+r.version+"\nVersion actuelle : "+current);
                    action.setText("Télécharger la mise à jour");
                    action.setEnabled(true);
                    action.setOnClickListener(v->download());
                });
            }catch(Exception e){display("Impossible de vérifier les mises à jour : "+e.getMessage());}
        }).start();
    }
    private void download(){
        if(release==null)return;
        action.setEnabled(false);action.setText("Téléchargement…");
        new Thread(()->{
            try{
                File apk=TrekMapUpdateManager.download(this,release);
                handler.post(()->{
                    downloaded=apk;
                    status.setText("APK téléchargé et contrôlé (SHA-256). Prêt à installer.");
                    action.setText("Installer la mise à jour");
                    action.setEnabled(true);
                    action.setOnClickListener(v->install());
                });
            }catch(Exception e){
                handler.post(()->{
                    status.setText("Échec du téléchargement : "+e.getMessage());
                    action.setText("Réessayer");action.setEnabled(true);
                    action.setOnClickListener(v->download());
                });
            }
        }).start();
    }
    private void install(){
        if(downloaded==null||!downloaded.exists())return;
        if(Build.VERSION.SDK_INT>=26&&!getPackageManager().canRequestPackageInstalls()){
            status.setText("Autorise TrekMap à installer des mises à jour depuis cette source, puis reviens ici et appuie à nouveau sur Installer.");
            Intent settings=new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:"+getPackageName()));
            startActivity(settings);
            return;
        }
        Uri uri=FileProvider.getUriForFile(this,getPackageName()+".apkprovider",downloaded);
        Intent intent=new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri,"application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        startActivity(intent); // Android displays final user confirmation.
    }
}
