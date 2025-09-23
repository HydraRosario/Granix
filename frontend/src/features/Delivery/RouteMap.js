import React from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { useAppContext } from '../../context/AppContext'; // Import useAppContext
import './RouteMap.css'; // Import the new CSS file

// Fix for default icon issue with webpack
delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl: require('leaflet/dist/images/marker-icon-2x.png'),
  iconUrl: require('leaflet/dist/images/marker-icon.png'),
  shadowUrl: require('leaflet/dist/images/marker-shadow.png'),
});

const RouteMap = () => {
  const { invoices, optimizedRoute, streetLevelPolyline } = useAppContext();

  // If an optimized route is available, use it. Otherwise, fall back to the general invoices list.
  const routeData = (optimizedRoute && optimizedRoute.length > 0) ? optimizedRoute : invoices;

  // Create a list of locations with valid coordinates for the markers.
  const locations = (routeData || [])
    .filter(point => point.coordinates && point.coordinates.latitude && point.coordinates.longitude)
    .map(point => ({
      lat: point.coordinates.latitude,
      lon: point.coordinates.longitude,
      address: point.delivery_address || point.parsed_data?.address,
      entity: point.commercial_entity || `Invoice ID: ${point.invoice_id}`,
    }));

  // Determine the polyline to display: prefer the street-level one, fallback to a straight line from stop coordinates.
  const polylinePositions = (streetLevelPolyline && streetLevelPolyline.length > 0) 
    ? streetLevelPolyline 
    : (locations.length > 1 ? locations.map(loc => [loc.lat, loc.lon]) : []);

  // If there are no locations at all, show a message.
  if (locations.length === 0) {
    return (
      <div className="no-map-data-message">
        <p>¡No hay ubicaciones para mostrar en el mapa! 🗺️</p>
        <p>Sube un informe de reparto o una factura para ver la ruta aquí. 📍</p>
      </div>
    );
  }

  // Center the map on the first location.
  const position = [locations[0].lat, locations[0].lon];

  return (
    <div className="route-map-container">
      <div className="map-view">
        <MapContainer center={position} zoom={13} style={{ height: '100%', width: '100%' }}>
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          />
          {/* Draw the street-level or straight-line polyline if it exists */}
          {polylinePositions.length > 0 && <Polyline positions={polylinePositions} color="#3498db" weight={5} />}
          
          {/* Draw markers for each location */}
          {locations.map((location, idx) => (
            <Marker key={idx} position={[location.lat, location.lon]}>
              <Popup>
                <strong>{location.entity}</strong><br />
                {location.address}
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </div>
  );
};

export default RouteMap;
