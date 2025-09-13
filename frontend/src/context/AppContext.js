import React, { createContext, useContext, useState } from 'react';
import { uploadInvoice } from '../api/api'; // Import the API function

const AppContext = createContext();

export const AppProvider = ({ children }) => {
  const [invoices, setInvoices] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const processInvoice = async (file) => {
    setIsLoading(true);
    setError(null); // Clear previous errors
    try {
      const newInvoices = await uploadInvoice(file);
      setInvoices((prevInvoices) => [...prevInvoices, ...newInvoices]);
    } catch (err) {
      setError(err.message || 'An unknown error occurred during upload.');
    } finally {
      setIsLoading(false);
    }
  };

  const contextValue = {
    invoices,
    isLoading,
    error,
    processInvoice,
  };

  return (
    <AppContext.Provider value={contextValue}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => {
  return useContext(AppContext);
};
