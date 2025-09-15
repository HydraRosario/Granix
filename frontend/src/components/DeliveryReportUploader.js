import React, { useState } from 'react';
import './DeliveryReportUploader.css';
import './CollapsibleCard.css'; // New import

const DeliveryReportUploader = () => {
  const [isOpen, setIsOpen] = useState(false);

  const toggleOpen = () => {
    setIsOpen(!isOpen);
  };

  return (
    <div className="collapsible-card"> {/* Changed class */}
      <div className="collapsible-header" onClick={toggleOpen}>
        <h2>Cargar Informe de Reparto</h2>
        <span className={`arrow ${isOpen ? 'open' : ''}`}>&gt;</span>
      </div>
      {isOpen && (
        <div className="collapsible-content">
          {/* Content for Delivery Report Uploader will go here */}
          <p>Aquí se cargará el informe de reparto.</p>
        </div>
      )}
    </div>
  );
};

export default DeliveryReportUploader;