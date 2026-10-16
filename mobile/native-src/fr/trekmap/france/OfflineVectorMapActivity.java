package fr.trekmap.france;

import android.app.Activity;
import android.annotation.SuppressLint;
import android.graphics.Color;
import android.os.Bundle;
import android.webkit.WebView;
import android.webkit.WebSettings;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebViewClient;
import android.net.Uri;
import android.widget.Toast;
import android.content.Intent;
import androidx.webkit.WebViewAssetLoader;
import org.json.JSONObject;
import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;

/**
 * Truly offline MapLibre GL WebView. Assets are packaged in the APK; vector
 * tiles are read from app-private storage via a bounded WebViewAssetLoader.
 * NO network requests or remote JavaScript are allowed inside this WebView.
 */
public class OfflineVectorMapActivity extends Activity {
    private static final String DOMAIN="appassets.androidplatform.net";
    private WebView web;
    private JSONObject route;
    private static WebResourceResponse json(String body){
        WebResourceResponse r=new WebResourceResponse("application/json","UTF-8",
            new ByteArrayInputStream(body.getBytes(StandardCharsets.UTF_8)));
        r.setResponseHeaders(new HashMap<String,String>(){{
            put("Cache-Control","no-store");put("Access-Control-Allow-Origin","*");
        }});
        return r;
    }
    private static WebResourceResponse denied(){
        return new WebResourceResponse("text/plain","UTF-8",404,"Not Found",
            new HashMap<>(),new ByteArrayInputStream(new byte[0]));
    }
    @SuppressLint("SetJavaScriptEnabled")
    @Override public void onCreate(Bundle b){
        super.onCreate(b);
        route=OfflineRouteStore.find(this,getIntent().getStringExtra("route_id"));
        if(route==null){Toast.makeText(this,"Trek enregistré introuvable",Toast.LENGTH_LONG).show();finish();return;}
        final WebViewAssetLoader loader=new WebViewAssetLoader.Builder()
            .setDomain(DOMAIN)
            .addPathHandler("/assets/",new WebViewAssetLoader.AssetsPathHandler(this))
            .addPathHandler("/tiles/",path->{
                try{
                    File f=OfflineTileStore.file(this,path);
                    if(!f.isFile()||f.length()==0)return denied();
                    WebResourceResponse r=new WebResourceResponse(
                        "application/x-protobuf",null,new FileInputStream(f));
                    r.setResponseHeaders(new HashMap<String,String>(){{
                        put("Cache-Control","public, max-age=31536000");
                        put("Access-Control-Allow-Origin","*");
                    }});
                    return r;
                }catch(Exception e){return denied();}
            })
            .addPathHandler("/data/",path->{
                if("route.json".equals(path))return json(route.toString());
                if("session.json".equals(path))return json(GpsTrackStore.read(this).toString());
                return denied();
            })
            .build();
        web=new WebView(this);
        web.setBackgroundColor(Color.rgb(229,238,232));
        WebSettings settings=web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(false);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.setWebViewClient(new WebViewClient(){
            @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest req){
                if(!DOMAIN.equals(req.getUrl().getHost()) || !"https".equals(req.getUrl().getScheme()))
                    return denied();
                WebResourceResponse response=loader.shouldInterceptRequest(req.getUrl());
                return response==null?denied():response;
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){
                Uri u=request.getUrl();
                return !("https".equals(u.getScheme())&&DOMAIN.equals(u.getHost()));
            }
        });
        setContentView(web);
        web.loadUrl("https://"+DOMAIN+"/assets/public/offline-map.html");
    }
    @Override protected void onDestroy(){
        if(web!=null){web.loadUrl("about:blank");web.destroy();web=null;}
        super.onDestroy();
    }
}
