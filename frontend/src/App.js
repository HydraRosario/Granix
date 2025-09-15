import React from 'react';
import './App.css';
import InvoiceUploader from './components/InvoiceUploader';
import DeliveryList from './components/DeliveryList';
import RouteMap from './components/RouteMap';
import logo from './assets/logo.png';

function App() {
  return (
    <div className="App">
      <header className="app-header">
        <img src={logo} alt="Granix Logistics Logo" className="app-logo" />
      </header>
      <div className="main-container">
        <div className="left-column">
          <InvoiceUploader />
          <DeliveryList />
        </div>
        <div className="right-column">
          <div className="right-column-card">
            <RouteMap />
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
