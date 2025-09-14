import React from 'react';
import { useAppContext } from '../context/AppContext';

const DeliveryList = () => {
  const { invoices, error } = useAppContext();

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
      <ul>
        {invoices.map((invoice) => (
          <li key={invoice.invoice_id} style={{ marginBottom: '10px', border: '1px solid #ccc', padding: '10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
              {/* Columna Izquierda */}
              <div>
                <strong>Nombre del cliente:</strong> {invoice.parsed_data.client_name || "Nombre no encontrado"}<br />
                <strong>Dirección de entrega:</strong> {invoice.parsed_data.address || "Dirección no encontrada"}<br />
              </div>
              {/* Columna Derecha */}
              <div style={{ textAlign: 'right' }}>
                <strong>ID de Factura:</strong> {invoice.invoice_id}<br />
                {invoice.url && (
                  <div>
                    <strong>Imagen:</strong> <a href={invoice.url} target="_blank" rel="noopener noreferrer">View Image</a>
                    <br />
                    <img src={invoice.url} alt="Invoice" style={{ maxWidth: '100px', maxHeight: '100px' }} />
                  </div>
                )}
              </div>
            </div>

            {invoice.parsed_data && (
              <>
                {invoice.parsed_data.product_items && invoice.parsed_data.product_items.length > 0 && (
                  <div style={{ marginTop: '10px', border: '1px solid #eee', padding: '5px' }}>
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
              </>
            )}
            {invoice.raw_ocr_text && (
              <div>
                <strong>Texto OCR:</strong>
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