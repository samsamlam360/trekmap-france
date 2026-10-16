package fr.trekmap.france;

import android.content.Context;
import org.json.JSONArray;
import org.json.JSONObject;

/** Private list of route geometries prepared while online. Never uploaded. */
final class OfflineRouteStore {
    private static final String PREF="trekmap_offline_routes_v1";
    private static final String FIELD="routes";
    private static final int MAX_ROUTES=12;
    private OfflineRouteStore(){}
    static JSONArray list(Context context){
        try {
            return new JSONArray(context.getSharedPreferences(PREF,Context.MODE_PRIVATE)
                .getString(FIELD,"[]"));
        }catch(Exception e){return new JSONArray();}
    }
    static boolean put(Context context,JSONObject route){
        if(!GpsTrackStore.isValidRoute(route))return false;
        JSONArray old=list(context), fresh=new JSONArray();
        try {
            JSONObject sanitized=new JSONObject();
            sanitized.put("id",route.optString("id"));
            sanitized.put("name",route.optString("name","Randonnée").substring(0,
                    Math.min(120,route.optString("name","Randonnée").length())));
            sanitized.put("region",route.optString("region","").substring(0,
                    Math.min(100,route.optString("region","").length())));
            sanitized.put("coords",route.getJSONArray("coords"));
            sanitized.put("preparedAt",System.currentTimeMillis());
            fresh.put(sanitized);
            for(int i=0;i<old.length() && fresh.length()<MAX_ROUTES;i++) {
                JSONObject entry=old.optJSONObject(i);
                if(entry!=null && GpsTrackStore.isValidRoute(entry)
                        && !entry.optString("id").equals(sanitized.optString("id")))
                    fresh.put(entry);
            }
            return context.getSharedPreferences(PREF,Context.MODE_PRIVATE)
                .edit().putString(FIELD,fresh.toString()).commit();
        }catch(Exception e){return false;}
    }
    static JSONObject find(Context c,String id){
        JSONArray a=list(c);
        for(int i=0;i<a.length();i++){
            JSONObject r=a.optJSONObject(i);
            if(r!=null && r.optString("id").equals(id)&&GpsTrackStore.isValidRoute(r))
                return r;
        }
        return null;
    }
}
