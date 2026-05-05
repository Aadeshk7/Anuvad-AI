import { useState } from 'react';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import { X, Eye, EyeOff, Loader2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Open the modal directly in 'login' or 'signup' mode */
  defaultMode?: 'login' | 'signup';
  /** Called after a successful login/signup */
  onSuccess?: () => void;
}

const backdrop: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
};
const panel: Variants = {
  hidden: { opacity: 0, scale: 0.93, y: 24 },
  visible: { opacity: 1, scale: 1, y: 0, transition: { type: 'spring', stiffness: 340, damping: 28 } },
  exit:   { opacity: 0, scale: 0.93, y: 24, transition: { duration: 0.18 } },
};

const AuthModal = ({ isOpen, onClose, onSuccess, defaultMode = 'login' }: AuthModalProps) => {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<'login' | 'signup'>(defaultMode);
  const [name, setName]         = useState('');
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd]   = useState(false);
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  const reset = () => {
    setName(''); setEmail(''); setPassword('');
    setError(''); setLoading(false); setShowPwd(false);
  };

  // Re-sync mode if parent changes defaultMode while modal is closed
  const switchMode = (m: 'login' | 'signup') => { reset(); setMode(m); };
  const handleClose = () => { reset(); setMode(defaultMode); onClose(); };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!email || !password) { setError('Please fill in all required fields.'); return; }
    if (mode === 'signup' && !name.trim()) { setError('Please enter your name.'); return; }
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return; }

    setLoading(true);
    try {
      if (mode === 'login') {
        await login(email.trim(), password);
      } else {
        await signup(name.trim(), email.trim(), password);
      }
      reset();
      onSuccess?.();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="backdrop"
          variants={backdrop}
          initial="hidden"
          animate="visible"
          exit="hidden"
          onClick={handleClose}
          className="fixed inset-0 z-[200] flex items-center justify-center px-4"
          style={{ background: 'rgba(26,26,46,0.55)', backdropFilter: 'blur(8px)' }}
        >
          <motion.div
            variants={panel}
            initial="hidden"
            animate="visible"
            exit="exit"
            onClick={e => e.stopPropagation()}
            className="relative w-full max-w-md rounded-[2.5rem] overflow-hidden"
            style={{
              background: 'rgba(255,255,255,0.92)',
              backdropFilter: 'blur(32px)',
              border: '1.5px solid rgba(124,58,237,0.14)',
              boxShadow: '0 32px 80px rgba(124,58,237,0.18), 0 2px 0 rgba(255,255,255,0.9) inset',
            }}
          >
            {/* Top gradient bar */}
            <div className="h-1.5 w-full" style={{ background: 'linear-gradient(90deg, #7c3aed, #d946ef, #a855f7)' }} />

            <div className="p-8">
              {/* Close */}
              <button
                onClick={handleClose}
                className="absolute top-6 right-6 w-9 h-9 rounded-xl flex items-center justify-center transition-all hover:bg-purple-50"
              >
                <X size={18} className="text-gray-400" />
              </button>

              {/* Header */}
              <div className="mb-8">
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4 shadow-lg"
                  style={{ background: 'linear-gradient(135deg, #7c3aed, #d946ef)' }}>
                  <img src="/logo.png" alt="" className="w-9 h-9 object-contain" />
                </div>
                <h2 className="text-2xl font-black text-[#1a1a2e] tracking-tight mb-1">
                  {mode === 'login' ? 'Welcome back' : 'Create account'}
                </h2>
                <p className="text-sm text-gray-400 font-medium">
                  {mode === 'login'
                    ? 'Sign in to continue to Anuvad'
                    : 'Start localizing content in 6 Indic languages'}
                </p>
              </div>

              {/* Tab switcher */}
              <div className="flex mb-6 bg-gray-100 rounded-2xl p-1">
                {(['login', 'signup'] as const).map(m => (
                  <button
                    key={m}
                    onClick={() => switchMode(m)}
                    className="flex-1 py-2.5 rounded-xl text-[13px] font-black transition-all"
                    style={mode === m ? {
                      background: 'white',
                      color: '#7c3aed',
                      boxShadow: '0 2px 12px rgba(124,58,237,0.10)',
                    } : { color: '#9ca3af' }}
                  >
                    {m === 'login' ? 'Sign In' : 'Sign Up'}
                  </button>
                ))}
              </div>

              {/* Form */}
              <form onSubmit={handleSubmit} className="space-y-4">
                <AnimatePresence initial={false}>
                  {mode === 'signup' && (
                    <motion.div
                      key="name-field"
                      initial={{ opacity: 0, height: 0, marginBottom: 0 }}
                      animate={{ opacity: 1, height: 'auto', marginBottom: 16 }}
                      exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                      style={{ overflow: 'hidden' }}
                    >
                      <label className="block text-[12px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">
                        Full Name
                      </label>
                      <input
                        type="text"
                        value={name}
                        onChange={e => setName(e.target.value)}
                        placeholder="John Doe"
                        className="w-full px-4 py-3.5 rounded-2xl text-[14px] font-semibold text-[#1a1a2e] outline-none transition-all"
                        style={{
                          background: 'rgba(124,58,237,0.04)',
                          border: '1.5px solid rgba(124,58,237,0.12)',
                        }}
                        onFocus={e => (e.target.style.borderColor = '#7c3aed')}
                        onBlur={e => (e.target.style.borderColor = 'rgba(124,58,237,0.12)')}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>

                <div>
                  <label className="block text-[12px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">
                    Email
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full px-4 py-3.5 rounded-2xl text-[14px] font-semibold text-[#1a1a2e] outline-none transition-all"
                    style={{
                      background: 'rgba(124,58,237,0.04)',
                      border: '1.5px solid rgba(124,58,237,0.12)',
                    }}
                    onFocus={e => (e.target.style.borderColor = '#7c3aed')}
                    onBlur={e => (e.target.style.borderColor = 'rgba(124,58,237,0.12)')}
                  />
                </div>

                <div>
                  <label className="block text-[12px] font-bold text-gray-500 uppercase tracking-widest mb-1.5">
                    Password
                  </label>
                  <div className="relative">
                    <input
                      type={showPwd ? 'text' : 'password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      placeholder="Min. 8 characters"
                      className="w-full px-4 py-3.5 pr-12 rounded-2xl text-[14px] font-semibold text-[#1a1a2e] outline-none transition-all"
                      style={{
                        background: 'rgba(124,58,237,0.04)',
                        border: '1.5px solid rgba(124,58,237,0.12)',
                      }}
                      onFocus={e => (e.target.style.borderColor = '#7c3aed')}
                      onBlur={e => (e.target.style.borderColor = 'rgba(124,58,237,0.12)')}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPwd(v => !v)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-purple-600 transition-colors"
                    >
                      {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>

                {/* Error */}
                <AnimatePresence initial={false}>
                  {error && (
                    <motion.p
                      key="error-msg"
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      className="text-[13px] font-bold text-red-500 bg-red-50 px-4 py-2.5 rounded-xl"
                    >
                      {error}
                    </motion.p>
                  )}
                </AnimatePresence>

                {/* Submit */}
                <motion.button
                  type="submit"
                  disabled={loading}
                  whileHover={!loading ? { scale: 1.02 } : {}}
                  whileTap={!loading ? { scale: 0.98 } : {}}
                  className="w-full py-4 rounded-2xl font-black text-white text-[13px] uppercase tracking-widest flex items-center justify-center gap-2 mt-2 disabled:opacity-60 disabled:cursor-not-allowed"
                  style={{ background: 'linear-gradient(135deg, #7c3aed, #d946ef)', boxShadow: '0 8px 24px rgba(124,58,237,0.28)' }}
                >
                  {loading ? (
                    <><Loader2 size={16} className="animate-spin" /> Processing...</>
                  ) : (
                    mode === 'login' ? 'Sign In' : 'Create Account'
                  )}
                </motion.button>
              </form>

              {/* Footer note */}
              <p className="text-center text-[12px] text-gray-400 mt-5 font-medium">
                {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
                <button onClick={() => switchMode(mode === 'login' ? 'signup' : 'login')}
                  className="font-black text-purple-600 hover:text-purple-800 transition-colors">
                  {mode === 'login' ? 'Sign Up' : 'Sign In'}
                </button>
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default AuthModal;
