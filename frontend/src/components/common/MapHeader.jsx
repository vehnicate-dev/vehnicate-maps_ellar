import { motion } from "framer-motion"
import { useNavigate } from "react-router-dom"

const MapHeader = () => {
  const navigate = useNavigate()

  return (
    <motion.header
      initial={{ y: -80 }}
      animate={{ y: 0 }}
      className="fixed top-0 w-full z-50 bg-black/95 backdrop-blur-xl border-b border-purple-500/20 shadow-lg"
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center">
        
        <div
          onClick={() => navigate("/")}
          className="flex items-center space-x-4 cursor-pointer"
        >
          <img
            src="/hn-logo_light.png"
            alt="Vehnicate Logo"
            className="h-10"
          />

          <span className="font-ledger text-2xl text-white">
            vehnicate
          </span>

          <span className="font-ledger text-xl bg-gradient-to-r from-pink-400 to-purple-500 bg-clip-text text-transparent">
            road explorer
          </span>
        </div>

      </div>
    </motion.header>
  )
}

export default MapHeader