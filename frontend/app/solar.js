// Solar position from NOAA Global Monitoring Laboratory, "General Solar Position
// Calculations" (Fourier-series equation of time and declination after Spencer, 1971).
// Used only for scene lighting and for switching streetlights at civil twilight.

const RAD = Math.PI / 180;

export function solarPosition(dayOfYear, localHours, latDeg, lonDeg, utcOffsetHours) {
  const g = (2 * Math.PI / 365) * (dayOfYear - 1 + (localHours - 12) / 24); // fractional year (rad)
  const eqtime = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g)
    - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));            // minutes
  const decl = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g)
    - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g)
    - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);               // rad
  const timeOffset = eqtime + 4 * lonDeg - 60 * utcOffsetHours;             // minutes
  const tst = localHours * 60 + timeOffset;                                  // true solar time
  const ha = (tst / 4 - 180) * RAD;                                          // hour angle
  const lat = latDeg * RAD;
  const cosZen = Math.sin(lat) * Math.sin(decl) + Math.cos(lat) * Math.cos(decl) * Math.cos(ha);
  const zenith = Math.acos(Math.min(1, Math.max(-1, cosZen)));
  // Azimuth westward from south (J. Meeus, Astronomical Algorithms, 2nd ed., eq. 13.5),
  // converted to clockwise from north.
  const fromSouth = Math.atan2(Math.sin(ha), Math.cos(ha) * Math.sin(lat) - Math.tan(decl) * Math.cos(lat));
  const azimuth = (fromSouth + Math.PI + 2 * Math.PI) % (2 * Math.PI);
  return { elevationDeg: 90 - zenith / RAD, azimuthDeg: azimuth / RAD };
}

export function dayOfYear(date = new Date()) {
  const start = Date.UTC(date.getFullYear(), 0, 0);
  return Math.floor((Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) - start) / 86400000);
}

// Civil twilight: sun 6 degrees below the horizon (NOAA definition).
export const CIVIL_TWILIGHT_DEG = -6;
