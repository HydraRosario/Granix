import React from 'react';
import './App.css';
import InvoiceUploader from './components/InvoiceUploader';
import DeliveryList from './components/DeliveryList';
import RouteMap from './components/RouteMap'; // Keep RouteMap for future use

function App() {
  return (
    <div className="App">
      <h1>Granix Logistics</h1>
      <InvoiceUploader />
      <DeliveryList />
      <RouteMap />
    </div>
  );
}

export default App;
