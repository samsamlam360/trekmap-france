package fr.trekmap.france;

import android.content.Intent;
import android.net.Uri;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Opens native GPS controls; never returns coordinates or starts tracking from JavaScript.
 * The user must explicitly press Start inside the native screen.
 */
@CapacitorPlugin(name = "TrekMapNativeGPS")
public class TrekMapNativeGpsPlugin extends Plugin {
    private boolean trustedHikePage(){
        String url=getBridge().getWebView().getUrl();
        Uri u=Uri.parse(url==null?"":url);
        return "https".equals(u.getScheme()) &&
                "trekmap-france.onrender.com".equals(u.getHost()) &&
                "/randonnee".equals(u.getPath()) && u.getPort()==-1;
    }
    @PluginMethod
    public void saveOfflineRoute(PluginCall call){
        if(!trustedHikePage()){call.reject("Cette action nécessite la page randonnée TrekMap.");return;}
        JSObject route=call.getObject("route");
        if(route==null||!GpsTrackStore.isValidRoute(route)){
            call.reject("Le trek doit avoir un tracé valide (maximum 6 000 points).");return;
        }
        if(!OfflineRouteStore.put(getContext(),route)){
            call.reject("Stockage Android impossible. Libère de l'espace et réessaie.");return;
        }
        JSObject result=new JSObject();result.put("saved",true);
        result.put("count",OfflineRouteStore.list(getContext()).length());
        call.resolve(result);
    }
    private boolean trustedTrekMapPage(){
        String url=getBridge().getWebView().getUrl();
        Uri u=Uri.parse(url==null?"":url);
        return "https".equals(u.getScheme()) &&
                "trekmap-france.onrender.com".equals(u.getHost()) &&
                ("/".equals(u.getPath())||"/randonnee".equals(u.getPath()))&&u.getPort()==-1;
    }
    @PluginMethod
    public void listOfflineRoutes(PluginCall call){
        if(!trustedTrekMapPage()){call.reject("Origine non autorisée.");return;}
        org.json.JSONArray all=OfflineRouteStore.list(getContext());
        org.json.JSONArray publicList=new org.json.JSONArray();
        for(int i=0;i<all.length();i++){
            org.json.JSONObject r=all.optJSONObject(i);
            if(r==null)continue;
            org.json.JSONObject item=new org.json.JSONObject();
            try{
                item.put("id",r.optString("id"));
                item.put("name",r.optString("name"));
                item.put("region",r.optString("region"));
                item.put("sections",OfflineTileStore.stages(r));
                publicList.put(item);
            }catch(org.json.JSONException ignored){}
        }
        JSObject res=new JSObject();res.put("routes",publicList);call.resolve(res);
    }
    @PluginMethod
    public void openOfflineRoute(PluginCall call){
        if(!trustedTrekMapPage()){call.reject("Origine non autorisée.");return;}
        String id=call.getString("id","");
        if(OfflineRouteStore.find(getContext(),id)==null){
            call.reject("Trek hors ligne introuvable.");return;
        }
        Intent intent=new Intent(getActivity(),OfflineRouteActivity.class);
        intent.putExtra("route_id",id);
        getActivity().runOnUiThread(()->getActivity().startActivity(intent));
        call.resolve();
    }
    @PluginMethod
    public void openOfflineDownload(PluginCall call){
        if(!trustedTrekMapPage()){call.reject("Origine non autorisée.");return;}
        String id=call.getString("id","");
        if(OfflineRouteStore.find(getContext(),id)==null){
            call.reject("Enregistre d'abord le trek dans Android.");return;
        }
        Intent intent=new Intent(getActivity(),OfflineDownloadActivity.class);
        intent.putExtra("route_id",id);
        getActivity().runOnUiThread(()->getActivity().startActivity(intent));
        call.resolve();
    }
    @PluginMethod
    public void openOfflineRoutes(PluginCall call){
        if(!trustedTrekMapPage()){call.reject("Action réservée à TrekMap.");return;}
        Intent intent=new Intent(getActivity(),OfflineTreksActivity.class);
        getActivity().runOnUiThread(()->getActivity().startActivity(intent));
        call.resolve();
    }
    @PluginMethod
    public void openTracker(PluginCall call) {
        if (!trustedHikePage()) {
            call.reject("Le GPS natif est réservé à la page randonnée sécurisée.");
            return;
        }
        JSObject requested = call.getObject("route");
        if (requested == null || !GpsTrackStore.isValidRoute(requested)) {
            call.reject("Le trek doit posséder un tracé GPS valide.");
            return;
        }
        // Bounded JSON (< 6000 coords) and private explicit Activity; not exposed to third-party pages.
        Intent intent = new Intent(getActivity(), GpsTrackActivity.class);
        intent.putExtra("trekmap_route", requested.toString());
        getActivity().runOnUiThread(() -> getActivity().startActivity(intent));
        call.resolve();
    }
}
