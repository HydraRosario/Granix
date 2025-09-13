import React from 'react';
import { useAppContext } from '../context/AppContext';

const DeliveryList = () => {
  const { invoices, error } = useAppContext();

  if (error) {
    return <div style={{ color: 'red' }}>Error: {error}</div>;
  }

  if (invoices.length === 0) {
    return <div>No hay facturas procesadas aún.</div>;
  }

  return (
    <div>
      <h2>Processed Invoices</h2>
      <ul>
        {invoices.map((invoice) => (
          <li key={invoice.invoice_id} style={{ marginBottom: '10px', border: '1px solid #ccc', padding: '10px' }}>
            <strong>Invoice ID:</strong> {invoice.invoice_id}<br />
            {invoice.url && (
              <div>
                <strong>Image:</strong> <a href={invoice.url} target="_blank" rel="noopener noreferrer">View Image</a>
                <br />
                <img src={invoice.url} alt="Invoice" style={{ maxWidth: '100px', maxHeight: '100px' }} />
              </div>
            )}
            {invoice.parsed_data && (
              <>
                <strong>Address:</strong> {invoice.parsed_data.address || "Dirección no encontrada"}<br />
                <strong>Total Amount:</strong> {invoice.parsed_data.total_amount !== null && invoice.parsed_data.total_amount !== undefined ? invoice.parsed_data.total_amount : "Monto no encontrado"}<br />
              </>
            )}
            {invoice.raw_ocr_text && (
              <div>
                <strong>Raw OCR Text:</strong>
                <textarea
                  readOnly
                  style={{ width: '100%', height: '100px', marginTop: '5px' }}
                  value={invoice.raw_ocr_text}
                />
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default DeliveryList;