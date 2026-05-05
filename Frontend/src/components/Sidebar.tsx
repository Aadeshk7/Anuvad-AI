import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard, Upload, RefreshCw, History, Globe
} from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';

const menuItems = [
  { icon: LayoutDashboard, label: 'Dashboard',  path: '/dashboard',  color: '#7c3aed' },
  { icon: Upload,          label: 'Upload',      path: '/upload',      color: '#a855f7' },
  { icon: RefreshCw,       label: 'Processing',  path: '/processing',  color: '#d946ef' },
  { icon: History,         label: 'History',     path: '/history',     color: '#b8a6ff' },
];

const Sidebar = () => {
  const navigate  = useNavigate();
  const location  = useLocation();

  return (
    <motion.div
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0,   opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="w-72 h-screen flex flex-col p-6 z-20 overflow-hidden"
      style={{
        background: 'rgba(255,255,255,0.45)',
        backdropFilter: 'blur(32px)',
        WebkitBackdropFilter: 'blur(32px)',
        borderRight: '1px solid rgba(174,172,182,0.18)',
        boxShadow: '4px 0 32px rgba(100,83,130,0.05)',
      }}
    >
      {/* Side-panel inner glow */}
      <div
        aria-hidden="true"
        className="absolute top-0 left-0 right-0 h-48 pointer-events-none"
        style={{ background: 'linear-gradient(180deg, rgba(222,200,255,0.18) 0%, transparent 100%)' }}
      />
      <div
        aria-hidden="true"
        className="absolute bottom-0 left-0 right-0 h-32 pointer-events-none"
        style={{ background: 'linear-gradient(0deg, rgba(177,242,184,0.12) 0%, transparent 100%)' }}
      />

      {/* Logo */}
      <motion.div
        whileHover={{ scale: 1.02 }}
        onClick={() => navigate('/')}
        className="flex items-center gap-2.5 mb-10 px-2 cursor-pointer relative z-10"
      >
        <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-white relative overflow-hidden shadow-lg shadow-purple-500/10 border border-purple-100">
          <img src="/logo.png" alt="Anuvad Logo" className="w-full h-full object-contain p-1.5" />
        </div>
        <span className="text-[22px] font-black tracking-tight text-[#2f2e36]">Anuvad</span>
      </motion.div>

      {/* Section label */}
      <p className="text-[9px] font-bold uppercase tracking-[0.22em] text-gray-400 mb-3 px-4 relative z-10">
        Navigation
      </p>

      {/* Nav Items */}
      <div className="flex-1 space-y-1 relative z-10">
        {menuItems.map((item, idx) => {
          const isActive = location.pathname === item.path;
          const Icon     = item.icon;
          return (
            <motion.div
              key={item.path}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.06, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              whileHover={{ x: 4 }}
              onClick={() => navigate(item.path)}
              className="relative flex items-center justify-between p-3.5 rounded-2xl cursor-pointer transition-all duration-200 group"
              style={isActive ? {
                background: 'rgba(255,255,255,0.75)',
                boxShadow: '0 4px 20px rgba(100,83,130,0.10), inset 0 1px 1px rgba(255,255,255,0.8)',
              } : { background: 'transparent' }}
            >
              {isActive && (
                <div
                  className="absolute inset-0 rounded-2xl pointer-events-none"
                  style={{ background: `linear-gradient(135deg, ${item.color}18 0%, transparent 70%)` }}
                />
              )}
              <div className="flex items-center gap-3.5">
                <div
                  className="w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200"
                  style={isActive ? {
                    background: `linear-gradient(135deg, ${item.color} 0%, #d946ef 100%)`,
                    boxShadow: `0 6px 16px ${item.color}40`,
                  } : { background: 'rgba(100,83,130,0.07)' }}
                >
                  <Icon size={17} className="transition-all duration-200" style={{ color: isActive ? '#fff' : '#7c3aed' }} />
                </div>
                <span className="text-[14px] font-semibold transition-all duration-200" style={{ color: isActive ? '#2f2e36' : '#6b6977' }}>
                  {item.label}
                </span>
              </div>
              <AnimatePresence>
                {isActive && (
                  <motion.div
                    layoutId="active-dot"
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    exit={{ scale: 0 }}
                    className="w-2 h-2 rounded-full"
                    style={{ background: item.color }}
                  />
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>

      {/* Divider */}
      <div
        className="my-4 relative z-10"
        style={{ height: 1, background: 'linear-gradient(90deg, transparent, rgba(174,172,182,0.25), transparent)' }}
      />

      {/* Engine Info Badge — replaces the old fake user card */}
      <motion.div
        whileHover={{ y: -2 }}
        className="relative z-10 flex items-center gap-3 p-4 rounded-2xl"
        style={{
          background: 'rgba(124,58,237,0.06)',
          border: '1px solid rgba(124,58,237,0.12)',
        }}
      >
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: 'linear-gradient(135deg, #7c3aed, #d946ef)' }}
        >
          <Globe size={16} color="#fff" />
        </div>
        <div>
          <p className="text-[13px] font-bold text-[#2f2e36]">Neural-Sync Engine</p>
          <p className="text-[11px] font-semibold" style={{ color: '#a855f7' }}>6 Indic Languages</p>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default Sidebar;
