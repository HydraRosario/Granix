import React, { useState } from 'react';
import { useAppContext } from '../context/AppContext';
import './InvoiceList.css';

const InvoiceList = () => {
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

  return (
    <div>
      <h2 className="processed-invoices-title">Facturas Procesadas</h2>
      <div className="invoice-list-container">
        {invoices.length === 0 ? (
          <div className="no-invoices-message">
            <p>¡Aún no hay facturas procesadas! 🧾</p>
            <p>Sube una para empezar. 🚀</p>
          </div>
        ) : (
          invoices.map((invoice, index) => {
            const isExpanded = expandedInvoices.includes(invoice.invoice_id || invoice.commercial_entity);
            return (
              <div key={invoice.invoice_id || `${invoice.commercial_entity}-${index}`} className={`invoice-card ${isExpanded ? 'expanded' : ''}`}>
                <div className={`invoice-header ${isExpanded ? 'expanded' : ''}`} onClick={() => toggleInvoice(invoice.invoice_id || invoice.commercial_entity)}>
                  <div className="invoice-header-info">
                    <span className="client-name">{invoice.parsed_data?.client_name || invoice.commercial_entity || "Cliente no encontrado"}</span>
                    <span>{invoice.parsed_data?.address || invoice.delivery_address || "Dirección no encontrada"}</span>
                  </div>
                  <div className={`indicator ${isExpanded ? 'expanded' : ''}`}>
                    &gt;
                  </div>
                </div>
                <div className={`invoice-details ${isExpanded ? 'expanded' : ''}`}>
                  <p><strong>ID:</strong> {invoice.invoice_id}</p>
                  {invoice.parsed_data?.product_items?.length > 0 && (
                    <table className="items-table">
                      <thead>
                        <tr>
                          <th>Artículo</th>
                          <th>Cantidad</th>
                          <th>Descripción</th>
                          <th>Precio</th>
                        </tr>
                      </thead>
                      <tbody>
                        {invoice.parsed_data.product_items.map((item, itemIndex) => (
                          <tr key={itemIndex}>
                            <td>{item.product_code}</td>
                            <td>{item.quantity}</td>
                            <td>{item.description}</td>
                            <td>{formatCurrency(item.item_total)}</td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr>
                          <td colSpan="3"><strong>IMPORTE TOTAL:</strong></td>
                          <td>{formatCurrency(invoice.parsed_data.total_amount)}</td>
                        </tr>
                      </tfoot>
                    </table>
                  )}
                  {invoice.url && (
                    <div style={{marginTop: '1rem'}}>
                      <a href={invoice.url} target="_blank" rel="noopener noreferrer">
                        <img src={invoice.url} alt="Invoice" style={{ width: '100%', borderRadius: '8px', cursor: 'pointer' }} />
                      </a>
                    </div>
                  )}
                  {invoice.raw_ocr_text && (
                    <div style={{marginTop: '1rem'}}>
                      <strong>Texto OCR:</strong>
                      <textarea
                        readOnly
                        className="ocr-textarea"
                        value={invoice.raw_ocr_text}
                      />
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default InvoiceList;
