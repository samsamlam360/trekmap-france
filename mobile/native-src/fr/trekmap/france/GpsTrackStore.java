package fr.trekmap.france;

import android.content.Context;
import android.location.Location;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

/** All GPS traces are stored ONLY inside private app preferences. No remote endpoint. */
final class GpsTrackStore {
    private static final String PREF = "trekmap_native_gps_v1";
    private static final String SESSION = "session";
    static final int MAX_ROUTE_POINTS = 6000;
    private static final int MAX_TRACK_POINTS = 18000;
    private GpsTrackStore() {}

    static boolean isValidRoute(JSONObject route) {
        if (route == null) return false;
        JSONArray coords = route.optJSONArray("coords");
        if (coords == null || coords.length() < 2 || coords.length() > MAX_ROUTE_POINTS) return false;
        String id = route.optString("id", "");
        if (id.length() == 0 || id.length() > 70) return false;
        for (int i=0; i<coords.length(); i++) {
            JSONArray p=coords.optJSONArray(i);
            if (p == null || p.length() < 2) return false;
            double lat=p.optDouble(0, Double.NaN),lon=p.optDouble(1,Double.NaN);
            if (!Double.isFinite(lat) || !Double.isFinite(lon) ||
                    Math.abs(lat)>85 || Math.abs(lon)>180) return false;
        }
        return true;
    }

    static JSONObject read(Context c) {
        try { return new JSONObject(c.getSharedPreferences(PREF,Context.MODE_PRIVATE)
                  .getString(SESSION, "{}")); }
        catch (JSONException e) { return new JSONObject(); }
    }
    static void save(Context c, JSONObject session) {
        // SharedPreferences writes an app-private atomic file. commit before acknowledging.
        c.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
                .putString(SESSION, session.toString()).commit();
    }
    static JSONObject initial(JSONObject route) throws JSONException {
        JSONObject o = new JSONObject();
        o.put("route", route);
        o.put("status", "ready");
        o.put("distance", 0);
        o.put("elapsed", 0);
        o.put("startEpoch", System.currentTimeMillis());
        o.put("accuracy", -1);
        o.put("offtrack", -1);
        o.put("remaining", -1);
        o.put("note", "Démarre le suivi pour enregistrer ta marche.");
        o.put("points", new JSONArray());
        return o;
    }
    static double meters(double lat1,double lon1,double lat2,double lon2) {
        float[] result = new float[1];
        Location.distanceBetween(lat1,lon1,lat2,lon2,result);
        return result[0];
    }
    /** Closest offset to a polyline; route coordinates are [latitude, longitude]. */
    static double[] nearest(double lat,double lon,JSONArray coords) {
        double best=Double.POSITIVE_INFINITY, along=0,total=0;
        for(int i=1;i<coords.length();i++) {
            JSONArray a=coords.optJSONArray(i-1), b=coords.optJSONArray(i);
            if(a==null || b==null) continue;
            double x1=a.optDouble(1),y1=a.optDouble(0);
            double x2=b.optDouble(1),y2=b.optDouble(0);
            double len=meters(y1,x1,y2,x2);
            if(len < 0.01) continue;
            double c=Math.cos(Math.toRadians((y1+y2+lat)/3.0));
            double dx=(x2-x1)*c,dy=y2-y1;
            double denom=dx*dx+dy*dy;
            double t=denom>0 ? Math.max(0, Math.min(1,
                    (((lon-x1)*c)*dx+(lat-y1)*dy)/denom)) : 0;
            double d=meters(lat,lon,y1+(y2-y1)*t,x1+(x2-x1)*t);
            if(d<best) { best=d; along=total+t*len; }
            total+=len;
        }
        return new double[]{best,Math.max(0,total-along)};
    }
    static void appendLocation(JSONObject session,Location loc,Location last,long lastElapsedMs) {
        try {
            final double acc=loc.hasAccuracy()?loc.getAccuracy():999;
            session.put("accuracy",Math.round(acc));
            if(acc>45) {
                session.put("note","Précision insuffisante. Attends un meilleur signal GPS.");
                return;
            }
            long now=android.os.SystemClock.elapsedRealtime();
            double step=last==null?0:loc.distanceTo(last);
            double seconds=last==null?10:Math.max(1,(now-lastElapsedMs)/1000d);
            if(last!=null && step/seconds>4.4) {
                session.put("note","Saut GPS ignoré : vitesse incohérente.");
                return;
            }
            if(last==null || step>=Math.max(6,Math.max(acc,last.getAccuracy())*0.65)) {
                if(last!=null) session.put("distance",session.optDouble("distance")+step);
                JSONArray points=session.optJSONArray("points");
                if(points==null) {points=new JSONArray();session.put("points",points);}
                if(points.length()>=MAX_TRACK_POINTS) {
                    session.put("note","Capacité de trace atteinte. Exporte le GPX.");
                    return;
                }
                JSONArray point=new JSONArray();
                point.put(loc.getLatitude()); point.put(loc.getLongitude());
                point.put(System.currentTimeMillis());
                points.put(point);
                session.put("lastLat",loc.getLatitude());
                session.put("lastLon",loc.getLongitude());
            }
            JSONObject route=session.optJSONObject("route");
            if(route!=null) {
                JSONArray coords=route.optJSONArray("coords");
                if(coords!=null) {
                    double[] off=nearest(loc.getLatitude(),loc.getLongitude(),coords);
                    session.put("offtrack",off[0]);
                    session.put("remaining",off[1]);
                    session.put("note",off[0]>Math.max(45,acc*1.8)
                            ? "Attention : tu sembles hors du tracé. Vérifie le terrain."
                            : "Tu sembles suivre le tracé.");
                }
            }
        } catch (JSONException e) {
            android.util.Log.e("TrekMapGPS","Failed to save GPS sample",e);
        }
    }

    static String toGpx(JSONObject session) {
        String name=session.optJSONObject("route")==null ? "Randonnée"
                : session.optJSONObject("route").optString("name","Randonnée");
        StringBuilder b=new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n");
        b.append("<gpx xmlns=\"http://www.topografix.com/GPX/1/1\" version=\"1.1\" creator=\"TrekMap France\"><trk><name>");
        b.append(xml(name)).append("</name><trkseg>");
        JSONArray p=session.optJSONArray("points");
        SimpleDateFormat iso=new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'",Locale.ROOT);
        iso.setTimeZone(TimeZone.getTimeZone("UTC"));
        if(p!=null) for(int i=0;i<p.length();i++) {
            JSONArray pos=p.optJSONArray(i);if(pos==null)continue;
            b.append("<trkpt lat=\"").append(pos.optDouble(0)).append("\" lon=\"")
                    .append(pos.optDouble(1)).append("\"><time>")
                    .append(iso.format(new Date(pos.optLong(2)))).append("</time></trkpt>");
        }
        return b.append("</trkseg></trk></gpx>").toString();
    }
    private static String xml(String s) {
        return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                .replace("\"","&quot;").replace("'","&apos;");
    }
}
