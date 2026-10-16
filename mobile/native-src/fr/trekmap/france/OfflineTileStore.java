package fr.trekmap.france;

import android.content.Context;
import android.location.Location;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;

/**
 * Local vector map cache. Stages are 25km long, so a long hike can be prepared
 * incrementally. Every click downloads a bounded subset: max 320 tiles/24MB.
 * Never bypasses the existing TrekMap /offline-tiles rate limits.
 */
final class OfflineTileStore {
    static final int MIN_Z=9,MAX_Z=14;
    static final int MAX_TILES_PER_ACTION=320;
    static final long MAX_BYTES_PER_ACTION=24L*1024*1024;
    static final long MAX_TOTAL_BYTES=650L*1024*1024; // safety margin on free phones
    private static final int STEP_METERS=350;
    private static final int STAGE_METERS=25000;
    private static final String URL_ROOT="https://trekmap-france.onrender.com/offline-tiles/";
    private OfflineTileStore(){}

    interface Reporter {
        void report(int done,int total,int downloaded,String message);
        boolean isCancelled();
    }
    static final class Progress {
        final int present,total;
        Progress(int a,int b){present=a;total=b;}
    }
    static int stages(JSONObject route) {
        JSONArray p=route.optJSONArray("coords");
        if(p==null || p.length()<2)return 0;
        double distance=0;
        for(int i=1;i<p.length();i++) {
            JSONArray a=p.optJSONArray(i-1),b=p.optJSONArray(i);
            if(a!=null&&b!=null)distance+=meters(a.optDouble(0),a.optDouble(1),b.optDouble(0),b.optDouble(1));
        }
        return Math.max(1,Math.min(2000,(int)Math.ceil(distance/STAGE_METERS)));
    }
    static LinkedHashSet<String> stageTiles(JSONObject route,int requestedStage){
        int stages=stages(route);
        if(requestedStage<0 || requestedStage>=stages)return new LinkedHashSet<>();
        JSONArray p=route.optJSONArray("coords");
        LinkedHashSet<String> tiles=new LinkedHashSet<>();
        double distance=0;
        double start=requestedStage*(double)STAGE_METERS;
        double end=(requestedStage+1)*(double)STAGE_METERS;
        for(int i=1;i<p.length();i++){
            JSONArray a=p.optJSONArray(i-1),b=p.optJSONArray(i);
            if(a==null||b==null)continue;
            double d=meters(a.optDouble(0),a.optDouble(1),b.optDouble(0),b.optDouble(1));
            double before=distance;distance+=d;
            if(distance<start || before>end || d<.01)continue;
            int n=Math.max(1,(int)Math.ceil(d/STEP_METERS));
            int from=Math.max(0,(int)Math.floor((start-before)/d*n));
            int to=Math.min(n,(int)Math.ceil((end-before)/d*n));
            for(int j=from;j<=to;j++){
                double t=j/(double)n,lat=a.optDouble(0)+(b.optDouble(0)-a.optDouble(0))*t,
                        lon=a.optDouble(1)+(b.optDouble(1)-a.optDouble(1))*t;
                for(int z=MIN_Z;z<=MAX_Z;z++){
                    int N=1<<z;
                    int x=(int)Math.floor((lon+180)/360*N);
                    double rad=Math.toRadians(Math.max(-85,Math.min(85,lat)));
                    int y=(int)Math.floor((1-Math.log(Math.tan(rad)+1/Math.cos(rad))/Math.PI)*N/2);
                    int radius=z>=12?1:0;
                    for(int dx=-radius;dx<=radius;dx++)for(int dy=-radius;dy<=radius;dy++){
                        int xx=x+dx,yy=y+dy;
                        if(xx>=0&&yy>=0&&xx<N&&yy<N)
                            tiles.add(z+"/"+xx+"/"+yy+".pbf");
                    }
                }
            }
        }
        return tiles;
    }
    private static double meters(double a,double b,double c,double d){
        float[] out=new float[1];Location.distanceBetween(a,b,c,d,out);return out[0];
    }
    static File file(Context c,String path){
        if(path==null||!path.matches("(9|10|11|12|13|14)/[0-9]{1,5}/[0-9]{1,5}\\.pbf"))
            throw new IllegalArgumentException("Invalid tile");
        String[] parts=path.replace(".pbf","").split("/");
        int z=Integer.parseInt(parts[0]),x=Integer.parseInt(parts[1]),y=Integer.parseInt(parts[2]);
        if(x>=(1<<z)||y>=(1<<z))throw new IllegalArgumentException("Invalid coordinates");
        return new File(c.getFilesDir(),"offline_tiles/"+path);
    }
    static Progress progress(Context c,JSONObject route,int stage){
        LinkedHashSet<String> tiles=stageTiles(route,stage);
        int n=0;for(String t:tiles) if(file(c,t).isFile()&&file(c,t).length()>0)n++;
        return new Progress(n,tiles.size());
    }
    static long cachedSize(Context c) {return sum(new File(c.getFilesDir(),"offline_tiles"));}
    private static long sum(File f){
        if(!f.exists())return 0;
        if(f.isFile())return f.length();
        long s=0;File[] files=f.listFiles();
        if(files!=null)for(File sub:files)s+=sum(sub);
        return s;
    }
    /**
     * Resumable, serial downloads: on every retry already downloaded tiles are skipped.
     * No user position or trek coordinates leave the device, only z/x/y tile IDs.
     */
    static void download(Context context,JSONObject route,int stage,Reporter reporter){
        LinkedHashSet<String> tiles=stageTiles(route,stage);
        int total=tiles.size(),completed=0,downloaded=0,errors=0;
        long bytes=0;
        for(String t:tiles){
            if(reporter.isCancelled()){reporter.report(completed,total,downloaded,"En pause. Reprends plus tard.");return;}
            File dest=file(context,t);
            if(dest.isFile()&&dest.length()>0){completed++;continue;}
            if(downloaded>=MAX_TILES_PER_ACTION || bytes>=MAX_BYTES_PER_ACTION){
                reporter.report(completed,total,downloaded,"Lot terminé. Relance pour continuer cette étape.");
                return;
            }
            if(cachedSize(context)>=MAX_TOTAL_BYTES){
                reporter.report(completed,total,downloaded,"Stockage cartographique de sécurité atteint (650 Mo).");
                return;
            }
            HttpURLConnection conn=null;
            File temp=null;
            try{
                conn=(HttpURLConnection)new URL(URL_ROOT+t).openConnection();
                conn.setConnectTimeout(8000);conn.setReadTimeout(11000);
                conn.setRequestProperty("User-Agent","TrekMapFrance-AndroidOffline/1.0 (https://trekmap-france.onrender.com)");
                conn.setRequestProperty("Accept","application/x-protobuf");
                int code=conn.getResponseCode();
                if(code==429){
                    reporter.report(completed,total,downloaded,"Limite horaire du serveur atteinte. Réessaie plus tard.");
                    return;
                }
                if(code!=200) {errors++;continue;}
                if(!dest.getParentFile().exists()&&!dest.getParentFile().mkdirs())
                    throw new Exception("Cannot create tile storage");
                temp=new File(dest.getParentFile(),dest.getName()+".part");
                long size=0;
                try(InputStream input=conn.getInputStream();FileOutputStream output=new FileOutputStream(temp)){
                    byte[] block=new byte[16384];int len;
                    while((len=input.read(block))>=0){
                        size+=len;
                        if(size>350000 || bytes+size>MAX_BYTES_PER_ACTION)throw new Exception("BUDGET");
                        output.write(block,0,len);
                    }
                    output.getFD().sync();
                }
                if(size==0)throw new Exception("EMPTY");
                if(!temp.renameTo(dest))throw new Exception("Unable to store tile");
                downloaded++;completed++;bytes+=size;
            }catch(Exception e){
                errors++;
                if("BUDGET".equals(e.getMessage())){
                    reporter.report(completed,total,downloaded,"Limite de 24 Mo atteinte. Reprends cette étape.");
                    return;
                }
            }finally{
                if(conn!=null)conn.disconnect();
                if(temp!=null&&temp.exists())temp.delete();
            }
            if((completed+errors)%8==0 || completed==total)
                reporter.report(completed,total,downloaded,"Téléchargement des chemins et cours d'eau…");
        }
        String summary=completed==total?"Carte de l'étape prête hors ligne.":
            "Partiel : "+(total-completed)+" tuiles manquantes, "+errors+" erreurs. Réessaie en Wi-Fi.";
        reporter.report(completed,total,downloaded,summary);
    }
}
