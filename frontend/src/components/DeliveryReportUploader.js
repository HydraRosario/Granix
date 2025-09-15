import React, { useState } from 'react';
import api from '../api/api'; // Import the API utility
import './DeliveryReportUploader.css';
import './CollapsibleCard.css';

const DeliveryReportUploader = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
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

    setLoading(true);
    setMessage('Cargando y procesando...');
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await api.post('/process_delivery_report', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      setMessage('Archivo procesado con éxito. Texto OCR extraído.');
      console.log('Respuesta del backend:', response.data);
      // Aquí podrías manejar la respuesta, por ejemplo, mostrar el raw_ocr_text
    } catch (error) {
      setMessage('Error al procesar el archivo.');
      console.error('Error al subir el archivo:', error);
    } finally {
      setLoading(false);
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
              disabled={loading} 
            />
            <button onClick={handleFileUpload} disabled={!file || loading} className="button">
              {loading ? 'Cargando...' : 'Cargar Informe'}
            </button>
          </div>
          {message && <p className="upload-message">{message}</p>}
        </div>
      )}
    </div>
  );
};

export default DeliveryReportUploader;