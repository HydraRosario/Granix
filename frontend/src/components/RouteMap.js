import React from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { useAppContext } from '../context/AppContext'; // Import useAppContext

// Fix for default icon issue with webpack
delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl: require('leaflet/dist/images/marker-icon-2x.png'),
  iconUrl: require('leaflet/dist/images/marker-icon.png'),
  shadowUrl: require('leaflet/dist/images/marker-shadow.png'),
});

const RouteMap = () => {
  const { invoices } = useAppContext(); // Get invoices from context

  // Extract locations from invoices
  const locations = invoices
    .filter(invoice => invoice.coordinates && invoice.coordinates.latitude && invoice.coordinates.longitude)
    .map(invoice => ({
      lat: invoice.coordinates.latitude,
      lon: invoice.coordinates.longitude,
      address: invoice.parsed_data.address, // Add address for popup
      invoice_id: invoice.invoice_id, // Add invoice_id for popup
    }));

  if (!locations || locations.length === 0) {
    return <p>No locations to display on the map.</p>;
  }

  // Use the first location as the center, or a default if no locations
  const position = [locations[0].lat, locations[0].lon];

  return (
    <MapContainer center={position} zoom={13} style={{ height: '100%', width: '100%' }}>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      />
      {locations.map((location, idx) => (
        <Marker key={idx} position={[location.lat, location.lon]}>
          <Popup>
            <strong>Invoice ID:</strong> {location.invoice_id}<br />
            <strong>Address:</strong> {location.address}<br />
            Latitude: {location.lat}<br />
            Longitude: {location.lon}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
};

export default RouteMap;
