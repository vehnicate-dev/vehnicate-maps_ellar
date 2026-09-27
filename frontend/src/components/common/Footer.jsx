import React from 'react'
import { motion } from 'framer-motion'
import { Linkedin, Instagram, Mail, ArrowUp, Heart } from 'lucide-react'
import { COMPANY_INFO } from '../../utils/constants'

const Footer = () => {
  const currentYear = new Date().getFullYear()

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <footer id="contact" className="relative bg-black pt-16 sm:pt-20 md:pt-24 pb-8 sm:pb-12 overflow-hidden">
      {/* BACKGROUND GRADIENTS AND PATCHES - CONSISTENT WITH OTHER SECTIONS */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-black via-purple-900/10 to-black"></div>
        <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-black"></div>
      </div>

      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute bottom-0 -left-24 sm:-left-32 lg:-left-48 w-48 h-48 sm:w-72 sm:h-72 lg:w-96 lg:h-96 bg-gradient-to-r from-pink-600/15 to-purple-600/10 rounded-full blur-3xl opacity-50" />
        <div className="absolute bottom-0 -right-24 sm:-right-32 lg:-right-48 w-40 h-40 sm:w-60 sm:h-60 lg:w-80 lg:h-80 bg-gradient-to-l from-purple-600/15 to-pink-600/10 rounded-full blur-3xl opacity-50" />
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* HEADER - CONSISTENT WITH OTHER SECTIONS */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
           transition={{ delay: 0.6, duration: 1, ease: [0.16, 1, 0.3, 1] }}
          viewport={{ once: true }}
          className="text-center mb-12 sm:mb-16 lg:mb-20"

        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl lg:text-6xl xl:text-7xl 2xl:text-8xl font-ledger font-bold mb-4 sm:mb-6 text-white leading-tight">
            doing good is <span className="bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">profitable.</span>
          </h2>
        </motion.div>

        {/* MAIN FOOTER CONTENT IN A GLASS CARD */}
        <motion.div
          initial={{ opacity: 0, y: 30, scale: 0.95 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          viewport={{ once: true }}
          className="bg-gray-900/40 backdrop-blur-lg rounded-2xl sm:rounded-3xl border border-white/10 p-6 sm:p-8 md:p-12 mb-8 sm:mb-12"
        >
          <div className="grid grid-cols-1 items-center gap-8 sm:gap-10 md:grid-cols-[1fr_1px_1fr] lg:gap-12">
            <div className="text-left">
              <h3 className="font-ledger text-2xl font-bold text-white sm:text-3xl">
                Ahoy!
              </h3>
              <p className="mt-4 max-w-md text-sm leading-relaxed text-gray-300 sm:text-base">
                Always remember, there&apos;s a home waiting for you and the
                others - we will be waiting for your next visit too!
              </p>
              <p className="mt-5 text-sm font-medium leading-relaxed text-white sm:text-base">
                Safe &amp; happy driving,
                <br />
                with <span className="text-pink-400">🩷</span>, vehnicate.
              </p>
            </div>

            <div
              aria-hidden="true"
              className="h-px w-full bg-white/15 md:h-full md:w-px"
            />

            <div className="text-left md:text-right">
              <div className="mb-4 sm:mb-6">
                <h3 className="mb-3 font-ledger text-2xl font-bold text-white sm:mb-4 sm:text-3xl">
                  vehnicate
                </h3>
                <p className="ml-auto max-w-md text-sm leading-relaxed text-gray-400 sm:text-base">
                  Building a gamified ecosystem that rewards being a good road
                  mate.
                </p>
              </div>
              <div className="flex space-x-2 sm:space-x-3 md:justify-end">
                <motion.a 
                  whileHover={{ scale: 1.1, y: -2 }} 
                  whileTap={{ scale: 0.9 }} 
                  href={COMPANY_INFO.social.linkedin} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  className="w-8 h-8 sm:w-10 sm:h-10 bg-white/10 rounded-lg flex items-center justify-center text-gray-300 hover:text-white hover:bg-purple-600/50 transition-all duration-300"
                >
                  <Linkedin size={16} className="sm:w-[18px] sm:h-[18px]" />
                </motion.a>
                <motion.a 
                  whileHover={{ scale: 1.1, y: -2 }} 
                  whileTap={{ scale: 0.9 }} 
                  href={COMPANY_INFO.social.instagram} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  className="w-8 h-8 sm:w-10 sm:h-10 bg-white/10 rounded-lg flex items-center justify-center text-gray-300 hover:text-white hover:bg-pink-600/50 transition-all duration-300"
                >
                  <Instagram size={16} className="sm:w-[18px] sm:h-[18px]" />
                </motion.a>
                <motion.a 
                  whileHover={{ scale: 1.1, y: -2 }} 
                  whileTap={{ scale: 0.9 }} 
                  href={`mailto:${COMPANY_INFO.social.email}`} 
                  className="w-8 h-8 sm:w-10 sm:h-10 bg-white/10 rounded-lg flex items-center justify-center text-gray-300 hover:text-white hover:bg-purple-600/50 transition-all duration-300"
                >
                  <Mail size={16} className="sm:w-[18px] sm:h-[18px]" />
                </motion.a>
              </div>
            </div>

          </div>
        </motion.div>

        {/* Bottom Bar */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.4 }}
          viewport={{ once: true }}
          className="border-t border-white/10 pt-6 sm:pt-8 flex flex-col sm:flex-row justify-between items-center text-center sm:text-left gap-4 sm:gap-0"
        >
          <p className="text-gray-400 text-xs sm:text-sm flex items-center order-2 sm:order-1">
            © {currentYear} vehnicate. Built with
            <motion.span
              animate={{ scale: [1, 1.2, 1] }}
              transition={{ duration: 1.5, repeat: Infinity, repeatType: "mirror" }}
              className="mx-1 sm:mx-1.5 text-pink-400"
            >
              <Heart size={12} className="fill-current sm:w-[14px] sm:h-[14px]" />
            </motion.span>
            by team vehnicate.
          </p>
          <motion.button
            whileHover={{ scale: 1.1, y: -3 }}
            whileTap={{ scale: 0.9 }}
            onClick={scrollToTop}
            className="w-8 h-8 sm:w-10 sm:h-10 bg-gradient-to-r from-purple-600 to-pink-600 rounded-full flex items-center justify-center text-white shadow-lg hover:shadow-xl hover:shadow-purple-500/40 transition-all duration-300 group order-1 sm:order-2"
            aria-label="Back to top"
          >
            <ArrowUp size={16} className="group-hover:-translate-y-0.5 transition-transform sm:w-[18px] sm:h-[18px]" />
          </motion.button>
        </motion.div>
      </div>
    </footer>
  )
}

export default Footer
