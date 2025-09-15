import React, { useState } from 'react';
import { useAppContext } from '../context/AppContext';
import './DeliveryList.css';

const DeliveryList = () => {
  const { invoices, error } = useAppContext();
  const [expandedInvoices, setExpandedInvoices] = useState([]);

  const toggleInvoice = (invoiceId) => {
    setExpandedInvoices(prev => 
      prev.includes(invoiceId) 
        ? prev.filter(id => id !== invoiceId) 
        : [...prev, invoiceId]
    );
  };

  const formatCurrency = (amount) => {
    const number = Number(amount);
    return new Intl.NumberFormat('es-AR', {
      style: 'currency',
      currency: 'ARS',
    }).format(number || 0);
  };

  if (error) {
    return <div style={{ color: 'red' }}>Error: {error}</div>;
  }

  if (invoices.length === 0) {
    return <div>No hay facturas procesadas aún.</div>;
  }

  return (
    <div>
      <h2>Facturas Procesadas</h2>
      <div className="invoice-list-container">
        {invoices.map((invoice) => {
          const isExpanded = expandedInvoices.includes(invoice.invoice_id);
          return (
            <div key={invoice.invoice_id} className="invoice-item">
              <div className="invoice-header" onClick={() => toggleInvoice(invoice.invoice_id)}>
                <div>
                  <strong>Cliente:</strong> {invoice.parsed_data.client_name || "N/A"}<br />
                  <strong>Dirección:</strong> {invoice.parsed_data.address || "N/A"}
                </div>
                <div className="indicator">
                  {isExpanded ? '-' : '+'}
                </div>
              </div>
              {isExpanded && (
                <div className="invoice-details">
                  <p><strong>ID de Factura:</strong> {invoice.invoice_id}</p>
                  {invoice.parsed_data && invoice.parsed_data.product_items && invoice.parsed_data.product_items.length > 0 && (
                    <div style={{ marginTop: '10px' }}>
                      <strong>Artículos:</strong>
                      <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '5px' }}>
                        <thead>
                          <tr>
                            <th style={{ border: '1px solid #ccc', padding: '8px', textAlign: 'left' }}>Artículo</th>
                            <th style={{ border: '1px solid #ccc', padding: '8px', textAlign: 'left' }}>Cantidad</th>
                            <th style={{ border: '1px solid #ccc', padding: '8px', textAlign: 'left' }}>Descripción</th>
                            <th style={{ border: '1px solid #ccc', padding: '8px', textAlign: 'left' }}>Precio</th>
                          </tr>
                        </thead>
                        <tbody>
                          {invoice.parsed_data.product_items.map((item, itemIndex) => (
                            <tr key={itemIndex}>
                              <td style={{ border: '1px solid #ccc', padding: '8px' }}>{item.product_code}</td>
                              <td style={{ border: '1px solid #ccc', padding: '8px' }}>{item.quantity}</td>
                              <td style={{ border: '1px solid #ccc', padding: '8px' }}>{item.description}</td>
                              <td style={{ border: '1px solid #ccc', padding: '8px' }}>{formatCurrency(item.item_total)}</td>
                            </tr>
                          ))}
                        </tbody>
                        <tfoot>
                          <tr>
                            <td colSpan="3" style={{ border: '1px solid #ccc', padding: '8px', textAlign: 'right' }}><strong>IMPORTE TOTAL:</strong></td>
                            <td style={{ border: '1px solid #ccc', padding: '8px' }}>{formatCurrency(invoice.parsed_data.total_amount)}</td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  )}
                  {invoice.url && (
                    <div style={{marginTop: '10px'}}>
                      <a href={invoice.url} target="_blank" rel="noopener noreferrer">
                        <img src={invoice.url} alt="Invoice" style={{ maxWidth: '600px', maxHeight: '600px', marginTop: '5px', cursor: 'pointer' }} />
                      </a>
                    </div>
                  )}
                  {invoice.raw_ocr_text && (
                    <div style={{marginTop: '10px'}}>
                      <strong>Texto OCR:</strong>
                      <textarea
                        readOnly
                        style={{ width: '100%', height: '100px', marginTop: '5px' }}
                        value={invoice.raw_ocr_text}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default DeliveryList;
