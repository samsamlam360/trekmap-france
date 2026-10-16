package fr.trekmap.france;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Build;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;

/** Strict, public GitHub release update source. Never accepts a URL from WebView JavaScript. */
final class TrekMapUpdateManager {
    private TrekMapUpdateManager() {}
    static final String API="https://api.github.com/repos/samsamlam360/trekmap-france/releases/latest";
    static final String ASSET="trekmap-france.apk";
    static final int MAX_APK_BYTES=90*1024*1024;

    static long installedVersion(Context context) throws Exception {
        PackageInfo info=context.getPackageManager().getPackageInfo(context.getPackageName(),0);
        if(Build.VERSION.SDK_INT>=28)return info.getLongVersionCode();
        return info.versionCode;
    }
    static final class Release {
        final long version;final String title,url,digest;
        Release(long code,String name,String link,String sha) {
            version=code;title=name;url=link;digest=sha;
        }
    }
    static Release latest() throws Exception {
        HttpURLConnection conn=(HttpURLConnection)new URL(API).openConnection();
        conn.setConnectTimeout(8000);conn.setReadTimeout(8000);
        conn.setRequestProperty("User-Agent","TrekMap-France-Android-Updater");
        conn.setRequestProperty("Accept","application/vnd.github+json");
        try {
            if(conn.getResponseCode()==404)return null; // No stable signed release yet.
            if(conn.getResponseCode()!=200)throw new Exception("GitHub ne répond pas ("+conn.getResponseCode()+")");
            byte[] raw=readLimited(conn.getInputStream(),800000);
            JSONObject release=new JSONObject(new String(raw,java.nio.charset.StandardCharsets.UTF_8));
            if(release.optBoolean("draft")||release.optBoolean("prerelease"))return null;
            String tag=release.optString("tag_name","");
            if(!tag.matches("android-v[0-9]{4,10}"))return null;
            long version=Long.parseLong(tag.substring("android-v".length()));
            JSONArray assets=release.optJSONArray("assets");
            if(assets==null)return null;
            for(int i=0;i<assets.length();i++) {
                JSONObject asset=assets.optJSONObject(i);
                if(asset==null||!ASSET.equals(asset.optString("name")))continue;
                String link=asset.optString("browser_download_url","");
                String sha=asset.optString("digest","").toLowerCase(Locale.ROOT);
                // Refuse any unsigned or unverifiable new download.
                if(!sha.matches("sha256:[0-9a-f]{64}"))return null;
                String expected="https://github.com/samsamlam360/trekmap-france/releases/download/"+tag+"/"+ASSET;
                if(!expected.equals(link))return null;
                return new Release(version,"TrekMap "+tag,link,sha.substring(7));
            }
            return null;
        } finally {conn.disconnect();}
    }
    private static byte[] readLimited(InputStream input,int cap) throws Exception {
        try(InputStream in=input;java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream()) {
            byte[] block=new byte[8192];int n;
            while((n=in.read(block))!=-1) {
                if(out.size()+n>cap)throw new Exception("Fichier trop volumineux");
                out.write(block,0,n);
            }
            return out.toByteArray();
        }
    }
    private static boolean allowedDownloadHost(String host) {
        return "github.com".equals(host) || "release-assets.githubusercontent.com".equals(host)
                || "objects.githubusercontent.com".equals(host);
    }
    static File download(Context context,Release release) throws Exception {
        File directory=new File(context.getCacheDir(),"updates");
        if(!directory.exists()&&!directory.mkdirs())throw new Exception("Dossier de mise à jour indisponible");
        File result=new File(directory,"trekmap-update.apk");
        if(result.exists()&&!result.delete())throw new Exception("Cache APK inaccessible");
        URL link=new URL(release.url);
        MessageDigest md=MessageDigest.getInstance("SHA-256");
        int redirects=0;
        try {
            while(true) {
                Uri uri=Uri.parse(link.toString());
                if(!"https".equals(uri.getScheme())||!allowedDownloadHost(uri.getHost()))
                    throw new SecurityException("Source APK non autorisée");
                HttpURLConnection conn=(HttpURLConnection)link.openConnection();
                conn.setInstanceFollowRedirects(false);
                conn.setConnectTimeout(10000);conn.setReadTimeout(22000);
                conn.setRequestProperty("User-Agent","TrekMap-France-Android-Updater");
                int code=conn.getResponseCode();
                if(code==301||code==302||code==303||code==307||code==308){
                    String location=conn.getHeaderField("Location");
                    conn.disconnect();
                    if(location==null||++redirects>5)throw new Exception("Redirections excessives");
                    link=new URL(link,location);
                    continue;
                }
                try {
                    if(code!=200)throw new Exception("Téléchargement HTTP "+code);
                    long bytes=0;
                    try(InputStream input=conn.getInputStream();FileOutputStream out=new FileOutputStream(result)) {
                        byte[] block=new byte[32768];int n;
                        while((n=input.read(block))!=-1){
                            bytes+=n;
                            if(bytes>MAX_APK_BYTES)throw new Exception("APK trop volumineux");
                            md.update(block,0,n);out.write(block,0,n);
                        }
                        out.getFD().sync();
                    }
                    StringBuilder hex=new StringBuilder();
                    for(byte b:md.digest())hex.append(String.format(Locale.ROOT,"%02x",b&0xff));
                    if(!hex.toString().equalsIgnoreCase(release.digest))throw new SecurityException("SHA-256 invalide");
                    if(bytes<100000)throw new SecurityException("APK incomplet");
                    return result;
                } finally {conn.disconnect();}
            }
        }catch(Exception e){result.delete();throw e;}
    }
}
