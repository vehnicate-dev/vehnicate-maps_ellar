import React from 'react'
import { motion } from 'framer-motion'
import { Linkedin, Instagram, Mail, MapPin, Phone, ArrowUp, Heart } from 'lucide-react'
import { COMPANY_INFO, NAVIGATION } from '../../utils/constants' // Assuming NAVIGATION is available for consistency

const Footer = () => {
  const currentYear = new Date().getFullYear()

  // Re-using the navigation constants for consistency if they match
  const footerLinks = {
    company: [
      { name: 'About Us', href: '#about' },
      { name: 'How It Works', href: '#working' },
    ],
    product: [
      { name: 'vehnicate App', href: 'waitlist' },
      { name: 'RPS System', href: '#' },
    ],
  }

  const scrollToSection = (href) => {
    if (href.startsWith('#')) {
      const element = document.querySelector(href)
      if (element) {
        element.scrollIntoView({ behavior: 'smooth' })
      }
    } else {
      window.open(href, '_blank', 'noopener,noreferrer')
    }
  }

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
            Finding the <span className="bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent "> calm </span> <br className="hidden sm:block" />
            <span className="sm:hidden"> </span>in the chaos
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
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-8 sm:gap-10 lg:gap-12">
            {/* Company Info */}
            <div className="lg:col-span-2">
              <div className="mb-4 sm:mb-6">
                <h3 className="font-ledger text-2xl sm:text-3xl font-bold text-white mb-3 sm:mb-4">
                  vehnicate
                </h3>
                <p className="text-sm sm:text-base text-gray-400 leading-relaxed max-w-md">
                  Building a gamified ecosystem that rewards safe and efficient driving, powered by cutting-edge data analytics.
                </p>
              </div>
              <div className="flex space-x-2 sm:space-x-3">
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

            {/* Link Sections */}
            {Object.entries(footerLinks).map(([category, links]) => (
              <div key={category}>
                <h4 className="font-ledger text-base sm:text-lg font-semibold text-white mb-4 sm:mb-6 capitalize relative">
                  {category}
                  <div className="absolute -bottom-1 sm:-bottom-2 left-0 w-6 sm:w-8 h-0.5 bg-gradient-to-r from-purple-500 to-pink-500 rounded-full"></div>
                </h4>
                <ul className="space-y-2 sm:space-y-3">
                  {links.map((link) => (
                    <li key={link.name}>
                      <button
                        onClick={() => scrollToSection(link.href)}
                        className="text-sm sm:text-base text-gray-400 transition-all duration-300 font-medium hover:bg-gradient-to-r hover:from-purple-400 hover:to-pink-500 hover:bg-clip-text hover:text-transparent text-left"
                      >
                        {link.name}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
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
