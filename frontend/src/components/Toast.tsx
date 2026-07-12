import { useState, useEffect } from 'react';
import './Toast.css';

type ToastType = 'success' | 'error' | 'info' | 'warning';

interface Toast {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
}

let toastListeners: ((toast: Toast) => void)[] = [];

export const toast = {
  success: (message: string, duration = 3000) => {
    const newToast: Toast = { id: Date.now().toString(), type: 'success', message, duration };
    toastListeners.forEach(listener => listener(newToast));
  },
  error: (message: string, duration = 5000) => {
    const newToast: Toast = { id: Date.now().toString(), type: 'error', message, duration };
    toastListeners.forEach(listener => listener(newToast));
  },
  info: (message: string, duration = 3000) => {
    const newToast: Toast = { id: Date.now().toString(), type: 'info', message, duration };
    toastListeners.forEach(listener => listener(newToast));
  },
  warning: (message: string, duration = 4000) => {
    const newToast: Toast = { id: Date.now().toString(), type: 'warning', message, duration };
    toastListeners.forEach(listener => listener(newToast));
  },
};

export default function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const listener = (newToast: Toast) => {
      setToasts(prev => [...prev, newToast]);
      if (newToast.duration) {
        setTimeout(() => {
          setToasts(prev => prev.filter(t => t.id !== newToast.id));
        }, newToast.duration);
      }
    };
    toastListeners.push(listener);
    return () => {
      toastListeners = toastListeners.filter(l => l !== listener);
    };
  }, []);

  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          <div className="toast-icon">
            {t.type === 'success' && '✓'}
            {t.type === 'error' && '✕'}
            {t.type === 'info' && 'ℹ'}
            {t.type === 'warning' && '⚠'}
          </div>
          <div className="toast-message">{t.message}</div>
          <button className="toast-close" onClick={() => removeToast(t.id)}>✕</button>
        </div>
      ))}
    </div>
  );
}
