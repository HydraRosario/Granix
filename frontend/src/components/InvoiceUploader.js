import React, { useState } from 'react';
import { useAppContext } from '../context/AppContext';
import './InvoiceUploader.css';

const InvoiceUploader = () => {
  const [selectedFile, setSelectedFile] = useState(null);
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

  return (
    <div className="invoice-uploader-card">
      <h2>Upload Invoice</h2>
      <div className="file-input-wrapper">
        <label htmlFor="file-upload" className="file-input-label">
          {selectedFile ? (
            <span className="file-name">{selectedFile.name}</span>
          ) : (
            <span>Drag & drop a file or click to select</span>
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
          {isLoading ? 'Uploading...' : 'Upload'}
        </button>
      </div>
    </div>
  );
};

export default InvoiceUploader;
