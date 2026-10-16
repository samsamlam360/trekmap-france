package fr.trekmap.france;
import android.content.Context;
import org.json.JSONArray;
import org.json.JSONObject;
/** Explicit user-created hiking landmarks, never inferred or claimed verified. */
final class OfflineWaypointStore {
    private static final String PREF="trekmap_waypoints_v1";
    static JSONArray list(Context c,String id){
        if(id==null||id.isEmpty())return new JSONArray();
        try{return new JSONArray(c.getSharedPreferences(PREF,Context.MODE_PRIVATE).getString(id,"[]"));}
        catch(Exception ignored){return new JSONArray();}
    }
    static boolean add(Context c,String id,String category,String label,double lat,double lon) {
        if(id==null||id.length()==0||id.length()>70||!Double.isFinite(lat)||!Double.isFinite(lon)||
            Math.abs(lat)>85||Math.abs(lon)>180)return false;
        JSONArray list=list(c,id);
        if(list.length()>=120)return false;
        try{
            JSONObject o=new JSONObject();
            o.put("category",category.substring(0,Math.min(32,category.length())));
            o.put("label",label.substring(0,Math.min(90,label.length())));
            o.put("lat",lat);o.put("lon",lon);o.put("time",System.currentTimeMillis());
            list.put(o);
            return c.getSharedPreferences(PREF,Context.MODE_PRIVATE).edit()
                .putString(id,list.toString()).commit();
        }catch(Exception e){return false;}
    }
}
