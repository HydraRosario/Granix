import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext'; // Import the context hook
import './DeliveryReportUploader.css';
import '../../components/CollapsibleCard.css';

const DeliveryReportUploader = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [file, setFile] = useState(null);
  const { isLoading, processDeliveryReport } = useAppContext(); // Get the processing function and loading state from context
  const [message, setMessage] = useState('');

  const toggleOpen = () => {
    setIsOpen(!isOpen);
    setMessage(''); // Clear message when collapsing/expanding
  };

  const onFileChange = (event) => {
    setFile(event.target.files[0]);
    setMessage('');
  };

  const handleFileUpload = async () => {
    if (!file) {
      setMessage('Por favor, selecciona un archivo primero.');
      return;
    }

    setMessage('Cargando y procesando el informe de reparto...');
    try {
      // Use the context function to process the file
      const response = await processDeliveryReport(file);
      setMessage('Informe de reparto procesado y ruta optimizada.');
      console.log('Respuesta del backend:', response);
    } catch (error) {
      setMessage('Error al procesar el informe de reparto.');
      console.error('Error al subir el archivo:', error);
    } 
  };

  return (
    <div className="collapsible-card">
      <div className="collapsible-header" onClick={toggleOpen}>
        <h2>Cargar Informe de Reparto</h2>
        <span className={`arrow ${isOpen ? 'open' : ''}`}>&gt;</span>
      </div>
      {isOpen && (
        <div className="collapsible-content">
          <div className="file-input-wrapper">
            <label htmlFor="delivery-file-upload" className="file-input-label">
              {file ? (
                <span className="file-name">{file.name}</span>
              ) : (
                <span>Haz click para seleccionar un archivo 📁</span>
              )}
            </label>
            <input 
              id="delivery-file-upload" 
              type="file" 
              className="file-input" 
              onChange={onFileChange} 
              disabled={isLoading} 
            />
            <button onClick={handleFileUpload} disabled={!file || isLoading} className="button">
              {isLoading ? 'Procesando...' : 'Optimizar Ruta'}
            </button>
          </div>
          {message && <p className="upload-message">{message}</p>}
        </div>
      )}
    </div>
  );
};

export default DeliveryReportUploader;
