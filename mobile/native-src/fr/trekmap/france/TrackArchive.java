package fr.trekmap.france;
import android.content.Context;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
/** Private, capped on-device hiking journal. Never uploaded to Neon. */
final class TrackArchive {
    private static final String PREF="trekmap_track_archive_v1";
    private static final String KEY="entries";
    private static final int MAX=24;
    private TrackArchive(){}
    static JSONArray list(Context c){
        try{return new JSONArray(c.getSharedPreferences(PREF,Context.MODE_PRIVATE).getString(KEY,"[]"));}
        catch(Exception e){return new JSONArray();}
    }
    static File photo(Context c,long date){
        return new File(new File(c.getFilesDir(),"photos"),"hike-"+date+".photo");
    }
    static File file(Context c,long date){
        return new File(new File(c.getFilesDir(),"tracks"),"hike-"+date+".gpx");
    }
    static void add(Context c,JSONObject session){
        JSONArray points=session.optJSONArray("points");
        if(points==null||points.length()<2)return;
        long timestamp=session.optLong("startEpoch");
        if(timestamp<=0)return;
        File f=file(c,timestamp);
        if(!f.getParentFile().exists()&&!f.getParentFile().mkdirs())return;
        try(FileOutputStream output=new FileOutputStream(f)){
            output.write(GpsTrackStore.toGpx(session).getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        }catch(Exception e){f.delete();return;}
        JSONArray original=list(c), saved=new JSONArray();
        JSONObject item=new JSONObject();
        try{
            JSONObject route=session.optJSONObject("route");
            item.put("date",timestamp);
            item.put("name",route==null?"Randonnée":route.optString("name","Randonnée"));
            item.put("routeId",route==null?"":route.optString("id",""));
            item.put("distance",session.optDouble("distance",0));
            item.put("duration",session.optLong("elapsed",0));
            item.put("ascent",session.optDouble("ascent",0));
            item.put("days",session.optInt("dayIndex",1));
            saved.put(item);
            for(int i=0;i<original.length();i++){
                JSONObject old=original.optJSONObject(i);
                if(old!=null&&old.optLong("date")!=timestamp&&saved.length()<MAX)saved.put(old);
                else if(old!=null&&saved.length()>=MAX){
                    file(c,old.optLong("date")).delete();
                    photo(c,old.optLong("date")).delete();
                }
            }
            c.getSharedPreferences(PREF,Context.MODE_PRIVATE).edit().putString(KEY,saved.toString()).commit();
        }catch(Exception ignored){}
    }
}
