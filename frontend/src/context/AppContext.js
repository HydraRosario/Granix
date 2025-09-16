import React, { createContext, useContext, useState } from 'react';
import api from '../api/api'; // Import the API utility

const AppContext = createContext();

export const AppProvider = ({ children }) => {
  const [invoices, setInvoices] = useState([]);
  const [optimizedRoute, setOptimizedRoute] = useState(null); // State for the optimized route
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Processes a single invoice file
  const processInvoice = async (file) => {
    setIsLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await api.post('/process_invoice', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      const newInvoices = response.data;
      setInvoices((prevInvoices) => [...prevInvoices, ...newInvoices]);
    } catch (err) {
      setError(err.message || 'An unknown error occurred during invoice processing.');
    } finally {
      setIsLoading(false);
    }
  };

  // Processes the delivery report file to get the optimized route
  const processDeliveryReport = async (file) => {
    setIsLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await api.post('/process_delivery_report', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      
      // The backend response contains the optimized route in response.data.route
      // and other details. We store the whole object.
      setOptimizedRoute(response.data); 
      
      // Optionally, if the response contains updated invoice data, you can update the invoices state
      if (response.data.route) {
        setInvoices(response.data.route);
      }

      return response.data; // Return data for local feedback in the component
    } catch (err) {
      setError(err.message || 'An unknown error occurred during delivery report processing.');
      throw err; // Re-throw error to be caught in the component
    } finally {
      setIsLoading(false);
    }
  };

  const contextValue = {
    invoices,
    optimizedRoute, // Provide the optimized route to consumers
    isLoading,
    error,
    processInvoice,
    processDeliveryReport, // Provide the new function
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
