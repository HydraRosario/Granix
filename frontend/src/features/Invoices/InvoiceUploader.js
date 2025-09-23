import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import './InvoiceUploader.css';
import '../../components/CollapsibleCard.css'; // New import

const InvoiceUploader = () => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isOpen, setIsOpen] = useState(false); // State for collapsible
  const { isLoading, processInvoice } = useAppContext();

  const handleFileChange = (event) => {
    setSelectedFile(event.target.files[0]);
  };

  const handleUpload = () => {
    if (selectedFile) {
      processInvoice(selectedFile);
      setSelectedFile(null); // Reset after upload
    }
  };

  const toggleOpen = () => {
    setIsOpen(!isOpen);
  };

  return (
    <div className="collapsible-card"> {/* Changed class */}
      <div className="collapsible-header" onClick={toggleOpen}>
        <h2>Cargar Factura</h2>
        <span className={`arrow ${isOpen ? 'open' : ''}`}>&gt;</span>
      </div>
      {isOpen && (
        <div className="collapsible-content">
          <div className="file-input-wrapper">
            <label htmlFor="file-upload" className="file-input-label">
              {selectedFile ? (
                <span className="file-name">{selectedFile.name}</span>
              ) : (
                <span>Haz click para seleccionar un archivo 📁</span>
              )}
            </label>
            <input 
              id="file-upload" 
              type="file" 
              className="file-input" 
              onChange={handleFileChange} 
              disabled={isLoading} 
            />
            <button onClick={handleUpload} disabled={!selectedFile || isLoading} className="button">
              {isLoading ? 'Cargando...' : 'Cargar'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default InvoiceUploader;
