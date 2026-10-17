package fr.trekmap.france;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.webkit.WebView;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Opens Android hiking tools only for TrekMap's verified HTTPS origins.
 * IMPORTANT: WebView.getUrl() MUST be called from the WebView UI thread.
 * Capacitor invokes plugin methods from its own execution context.
 * DB/JSON/tiles computations run off the Android main thread; only URL
 * validation and Activity starts touch the UI thread.
 */
@CapacitorPlugin(name = "TrekMapNativeGPS")
public class TrekMapNativeGpsPlugin extends Plugin {
    private static final ExecutorService IO=Executors.newSingleThreadExecutor(r->{
        Thread t=new Thread(r,"trekmap-native-route-io");
        t.setDaemon(true);
        return t;
    });
    private interface Task { void run() throws Exception; }

    private void permitted(PluginCall call,boolean hikeOnly,Task action){
        final Activity activity=getActivity();
        if(activity==null||activity.isFinishing()){
            call.reject("TrekMap Android n'est plus au premier plan.");return;
        }
        // A WebView method on the CapacitorPlugins worker causes Android's
        // WebView thread checker to throw, and can close the whole app.
        activity.runOnUiThread(()->{
            try {
                final WebView web=getBridge()==null?null:getBridge().getWebView();
                final String current=web==null?null:web.getUrl();
                final Uri uri=Uri.parse(current==null?"":current);
                final String path=uri.getPath();
                final boolean secure="https".equals(uri.getScheme())
                        && "trekmap-france.onrender.com".equals(uri.getHost())
                        && uri.getPort()==-1;
                // Capacitor serves the bundled dashboard from HTTPS localhost.
                // Remote TrekMap may still use the bridge only on its own trusted pages.
                final boolean local="https".equals(uri.getScheme())
                        && "localhost".equals(uri.getHost()) && uri.getPort()==-1
                        && ("/".equals(path) || "/index.html".equals(path));
                final boolean accepted=(secure && ("/randonnee".equals(path) ||
                        (!hikeOnly && "/".equals(path)))) || (!hikeOnly && local);
                if(!accepted){
                    call.reject(hikeOnly?"Action réservée au mode randonnée TrekMap.":
                            "Cette action doit être ouverte depuis TrekMap France.");return;
                }
                IO.execute(()->{
                    try{action.run();}
                    catch(Exception e){call.reject("Action Android interrompue : "+e.getMessage());}
                });
            }catch(Exception e){
                call.reject("Impossible de vérifier la page Android : "+e.getMessage());
            }
        });
    }
    private void launch(PluginCall call,Intent intent){
        final Activity activity=getActivity();
        if(activity==null||activity.isFinishing()){
            call.reject("TrekMap a été fermé : rouvre l'application.");return;
        }
        activity.runOnUiThread(()->{
            try {
                if(activity.isFinishing()||activity.isDestroyed()){
                    call.reject("TrekMap a été fermé : réessaie.");return;
                }
                activity.startActivity(intent);
                call.resolve();
            }catch(Exception e){
                call.reject("Écran Android inaccessible : "+e.getMessage());
            }
        });
    }

    /** Online features load only after a deliberate tap; no cold-start dependency. */
    @PluginMethod
    public void openOnline(PluginCall call){
        permitted(call,false,()->{
            android.net.ConnectivityManager cm=(android.net.ConnectivityManager)
                    getContext().getSystemService(android.content.Context.CONNECTIVITY_SERVICE);
            android.net.NetworkCapabilities caps=cm==null?null:
                    cm.getNetworkCapabilities(cm.getActiveNetwork());
            if(caps==null||!caps.hasCapability(
                    android.net.NetworkCapabilities.NET_CAPABILITY_VALIDATED)){
                call.reject("Pas de connexion Internet vérifiée. La carte locale reste disponible.");
                return;
            }
            navigate(call,"https://trekmap-france.onrender.com/");
        });
    }

    /** Return to the bundled, network-independent application dashboard. */
    @PluginMethod
    public void openLocalHome(PluginCall call){
        permitted(call,false,()->navigate(call,"https://localhost/"));
    }

    private void navigate(PluginCall call,String url){
        Activity activity=getActivity();
        if(activity==null){call.reject("Application fermée.");return;}
        activity.runOnUiThread(()->{
            try{
                WebView web=getBridge()==null?null:getBridge().getWebView();
                if(web==null){call.reject("Écran Android indisponible.");return;}
                web.loadUrl(url);
                call.resolve();
            }catch(Exception e){call.reject("Navigation impossible : "+e.getMessage());}
        });
    }

    @PluginMethod
    public void saveOfflineRoute(PluginCall call){
        permitted(call,true,()->{
            JSObject route=call.getObject("route");
            if(route==null||!GpsTrackStore.isValidRoute(route)){
                call.reject("Trek invalide. Maximum 6 000 coordonnées.");return;
            }
            if(!OfflineRouteStore.put(getContext(),route)){
                call.reject("Enregistrement local impossible. Vérifie l'espace disponible.");return;
            }
            JSObject result=new JSObject();
            result.put("saved",true);
            result.put("count",OfflineRouteStore.list(getContext()).length());
            call.resolve(result);
        });
    }

    @PluginMethod
    public void listOfflineRoutes(PluginCall call){
        permitted(call,false,()->{
            JSONArray all=OfflineRouteStore.list(getContext()),publicList=new JSONArray();
            for(int i=0;i<all.length();i++){
                JSONObject route=all.optJSONObject(i);
                if(route==null||!GpsTrackStore.isValidRoute(route))continue;
                JSONObject item=new JSONObject();
                item.put("id",route.optString("id"));
                item.put("name",route.optString("name"));
                item.put("region",route.optString("region"));
                item.put("sections",OfflineTileStore.stages(route));
                publicList.put(item);
            }
            JSObject res=new JSObject();res.put("routes",publicList);
            call.resolve(res);
        });
    }

    @PluginMethod
    public void openOfflineRoute(PluginCall call){
        permitted(call,false,()->{
            String id=call.getString("id","");
            if(OfflineRouteStore.find(getContext(),id)==null){
                call.reject("Trek hors ligne introuvable.");return;
            }
            Intent intent=new Intent(getContext(),OfflineRouteActivity.class);
            intent.putExtra("route_id",id);
            launch(call,intent);
        });
    }

    @PluginMethod
    public void openOfflineDownload(PluginCall call){
        permitted(call,false,()->{
            String id=call.getString("id","");
            if(OfflineRouteStore.find(getContext(),id)==null){
                call.reject("Enregistre d'abord ce trek dans Android.");return;
            }
            Intent intent=new Intent(getContext(),OfflineDownloadActivity.class);
            intent.putExtra("route_id",id);
            launch(call,intent);
        });
    }

    @PluginMethod
    public void openOfflineJournal(PluginCall call){
        permitted(call,false,()->launch(call,
                new Intent(getContext(),TrackArchiveActivity.class)));
    }

    @PluginMethod
    public void openOfflineMap(PluginCall call){
        permitted(call,false,()->{
            Intent intent=new Intent(getContext(),OfflineVectorMapActivity.class);
            String id=call.getString("id","");
            if(!id.isEmpty()&&OfflineRouteStore.find(getContext(),id)!=null){
                intent.putExtra("route_id",id);
            }
            launch(call,intent);
        });
    }

    @PluginMethod
    public void openOfflineRoutes(PluginCall call){
        permitted(call,false,()->{
            Intent intent=new Intent(getContext(),OfflineTreksActivity.class);
            intent.putExtra("list_only",true);
            launch(call,intent);
        });
    }

    @PluginMethod
    public void openTracker(PluginCall call){
        permitted(call,true,()->{
            JSObject route=call.getObject("route");
            if(route==null||!GpsTrackStore.isValidRoute(route)){
                call.reject("Tracé GPS invalide.");return;
            }
            Intent intent=new Intent(getContext(),GpsTrackActivity.class);
            intent.putExtra("trekmap_route",route.toString());
            launch(call,intent);
        });
    }
}
