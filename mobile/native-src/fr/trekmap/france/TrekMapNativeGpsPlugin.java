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
    @PluginMethod
    public void openOfflineRoutes(PluginCall call){
        if(!trustedHikePage()){call.reject("Action réservée à TrekMap.");return;}
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
