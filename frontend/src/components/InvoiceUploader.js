import React, { useState } from 'react';
import { useAppContext } from '../context/AppContext';

const InvoiceUploader = () => {
  const [selectedFile, setSelectedFile] = useState(null);
  const { isLoading, processInvoice } = useAppContext(); // processInvoice will be implemented later

  const handleFileChange = (event) => {
    setSelectedFile(event.target.files[0]);
  };

  const handleUpload = () => {
    if (selectedFile) {
      processInvoice(selectedFile); // Call the context function
    }
  };

  return (
    <div>
      <h2>Upload Invoice</h2>
      <input type="file" onChange={handleFileChange} disabled={isLoading} />
      <button onClick={handleUpload} disabled={isLoading}>
        {isLoading ? 'Uploading...' : 'Upload'}
      </button>
      {/* We will display error messages here later */}
    </div>
  );
};

export default InvoiceUploader;