import React from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { useAppContext } from '../context/AppContext'; // Import useAppContext
import './RouteMap.css'; // Import the new CSS file

// Fix for default icon issue with webpack
delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl: require('leaflet/dist/images/marker-icon-2x.png'),
  iconUrl: require('leaflet/dist/images/marker-icon.png'),
  shadowUrl: require('leaflet/dist/images/marker-shadow.png'),
});

const RouteMap = () => {
  const { invoices, optimizedRoute } = useAppContext();

  // Correctly access the optimized route from the backend response structure
  // It's located at optimizedRoute.parsed_report_data.optimized_route
  const actualOptimizedRoute = optimizedRoute?.parsed_report_data?.optimized_route;

  // Determine which data to display: the actual optimized route if available, otherwise fallback to individual invoices
  const routeData = (actualOptimizedRoute && Array.isArray(actualOptimizedRoute))
    ? actualOptimizedRoute
    : invoices;

  // Determine if we have a valid optimized route to display the timeline and polyline
  const hasOptimizedRoute = (actualOptimizedRoute && Array.isArray(actualOptimizedRoute) && actualOptimizedRoute.length > 0);

  const locations = (routeData || [])
    .filter(point => point.coordinates && point.coordinates.latitude && point.coordinates.longitude)
    .map(point => ({
      lat: point.coordinates.latitude,
      lon: point.coordinates.longitude,
      address: point.delivery_address || point.parsed_data?.address,
      entity: point.commercial_entity || `Invoice ID: ${point.invoice_id}`,
    }));

  if (!locations || locations.length === 0) {
    return (
      <div className="no-map-data-message">
        <p>¡No hay ubicaciones para mostrar en el mapa! 🗺️</p>
        <p>Sube un informe de reparto o una factura para ver la ruta aquí. 📍</p>
      </div>
    );
  }

  const position = [locations[0].lat, locations[0].lon];
  const polylinePositions = locations.map(loc => [loc.lat, loc.lon]);

  return (
    <div className="route-map-container">
      <div className="map-view">
        <MapContainer center={position} zoom={13} style={{ height: '100%', width: '100%' }}>
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          />
          {hasOptimizedRoute && <Polyline positions={polylinePositions} color="blue" />}
          
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
