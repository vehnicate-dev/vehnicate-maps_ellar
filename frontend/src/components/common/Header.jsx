import React, { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Menu, X } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'

const NAVIGATION = [
  { name: 'What', href: '#home' },
  { name: 'Why', href: '#why' },
  { name: 'App', href: '#app' },
  { name: 'Ellar', href: '#ellar' },
  { name: 'vMN', href: '#vmn' },
  { name: 'Map', href: '#maps' },
  { name: 'Contact', href: '#contact' },
]

const TIMES_FONT = {
  fontFamily: '"Times New Roman", Times, serif',
}

const Header = () => {
  const [isScrolled, setIsScrolled] = useState(false)
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 50)
    }

    window.addEventListener('scroll', handleScroll)

    return () => {
      window.removeEventListener('scroll', handleScroll)
    }
  }, [])

  /*
   * ============================================================
   * NAVIGATION
   * ============================================================
   *
   * If already on Home:
   *     Smoothly scroll to the requested section.
   *
   * If on another page:
   *     Navigate to Home first, then scroll to the section.
   */

  const scrollToSection = (href) => {
    setIsMobileMenuOpen(false)

    const scrollToElement = () => {
      const element = document.querySelector(href)

      if (!element) return

      const offset = href === '#ellar' ? -120 : href === '#why' ? -80 : 0

      /*
       * Use the global Lenis instance created in App.jsx.
       *
       * This gives header navigation the exact same smooth
       * scrolling behavior as normal page scrolling.
       */

      if (window.__lenis) {
        window.__lenis.scrollTo(element, {
          offset,
          duration: 1.4,
        })
      } else {
        /*
         * Fallback in case Lenis isn't available yet.
         */

        window.scrollTo({
          top: element.getBoundingClientRect().top + window.scrollY + offset,
          behavior: 'smooth',
        })
      }
    }

    /*
     * Already on Home
     */

    if (location.pathname === '/') {
      scrollToElement()
      return
    }

    /*
     * Coming from another page.
     *
     * Navigate to Home first, then wait briefly for the Home
     * component to mount before finding the section.
     */

    navigate('/')

    setTimeout(() => {
      scrollToElement()
    }, 100)
  }

  return (
    <motion.header
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      className={`fixed top-0 w-full z-50 transition-all duration-500 ${
        isScrolled
          ? 'bg-black/95 backdrop-blur-xl border-b border-purple-500/20 shadow-2xl shadow-purple-500/10'
          : 'bg-transparent'
      }`}
    >

      {/* BACKGROUND PATCHES FOR HEADER */}

      {isScrolled && (
        <div className="absolute inset-0 overflow-hidden pointer-events-none">

          <div className="absolute top-0 -left-10 sm:-left-20 w-20 sm:w-40 h-16 sm:h-20 bg-gradient-to-r from-purple-600/15 to-pink-600/10 rounded-full blur-2xl opacity-60" />

          <div className="absolute top-0 -right-10 sm:-right-20 w-20 sm:w-40 h-16 sm:h-20 bg-gradient-to-l from-pink-600/15 to-purple-600/10 rounded-full blur-2xl opacity-60" />

        </div>
      )}

      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">

        <div className="flex items-center justify-between h-14 sm:h-16">

          {/* BRAND */}

          <div className="flex min-w-0 items-center">
            <motion.div
              id="header-brand"
              whileTap={{ scale: 0.95 }}
              className="flex shrink-0 cursor-pointer items-center"
              onClick={() => scrollToSection('#home')}
            >

            <img
              src="/hn-logo_light.png"
              alt="Vehnicate Logo"
              className="h-9 sm:h-10 md:h-12 mr-2 sm:mr-3"
              onError={(e) => {
                e.target.onerror = null
                e.target.src =
                  'https://placehold.co/40x40/000000/FFFFFF?text=Error'
              }}
            />

            {/* IMPORTANT:
                This is the exact wordmark that the splash targets.
            */}

            <motion.span
              id="header-wordmark"
              className="text-xl sm:text-2xl md:text-3xl text-white"
              style={TIMES_FONT}
            >
              vehnicate
            </motion.span>

            </motion.div>

          </div>


          {/* DESKTOP NAVIGATION */}

          <div className="hidden md:block">

            <div
              className="flex items-center space-x-4 lg:space-x-6 xl:space-x-8"
              style={TIMES_FONT}
            >

              {NAVIGATION.map((item, index) => (
                <motion.button
                  key={item.name}

                  initial={{
                    opacity: 0,
                    y: -20,
                  }}

                  animate={{
                    opacity: 1,
                    y: 0,
                  }}

                  transition={{
                    duration: 0.5,
                    delay: index * 0.1,
                  }}

                  whileHover={{
                    scale: 1.05,
                    y: -2,
                  }}

                  whileTap={{
                    scale: 0.95,
                  }}

                  onClick={() => scrollToSection(item.href)}

                  className="text-sm lg:text-base xl:text-lg text-gray-300 transition-all duration-300 relative group font-medium hover:bg-gradient-to-r hover:from-purple-400 hover:to-pink-500 hover:bg-clip-text hover:text-transparent"
                >

                  {item.name}

                  <motion.span
                    className="absolute -bottom-1 left-0 h-0.5 bg-gradient-to-r from-purple-500 to-pink-500 rounded-full"

                    initial={{
                      width: 0,
                    }}

                    whileHover={{
                      width: '100%',
                    }}

                    transition={{
                      duration: 0.3,
                      ease: 'easeInOut',
                    }}
                  />

                </motion.button>
              ))}

            </div>

          </div>


          {/* MOBILE MENU BUTTON */}

          <div className="md:hidden">

            <motion.button
              whileHover={{
                scale: 1.1,
              }}

              whileTap={{
                scale: 0.9,
              }}

              onClick={() =>
                setIsMobileMenuOpen(!isMobileMenuOpen)
              }

              className={`p-2 rounded-lg transition-all duration-300 ${
                isMobileMenuOpen
                  ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white shadow-lg shadow-purple-500/50'
                  : 'text-white hover:bg-white/10'
              }`}
            >

              <motion.div
                animate={{
                  rotate: isMobileMenuOpen ? 90 : 0,
                }}

                transition={{
                  duration: 0.3,
                }}
              >

                {isMobileMenuOpen ? (
                  <X
                    size={20}
                    className="sm:w-6 sm:h-6"
                  />
                ) : (
                  <Menu
                    size={20}
                    className="sm:w-6 sm:h-6"
                  />
                )}

              </motion.div>

            </motion.button>

          </div>

        </div>

        {/* MOBILE NAVIGATION */}

        <motion.div
          initial={{
            opacity: 0,
            height: 0,
            y: -20,
          }}

          animate={{
            opacity: isMobileMenuOpen ? 1 : 0,
            height: isMobileMenuOpen ? 'auto' : 0,
            y: isMobileMenuOpen ? 0 : -20,
          }}

          transition={{
            duration: 0.4,
            ease: 'easeInOut',
          }}

          className="md:hidden overflow-hidden"
        >

          <motion.div
            className="relative mt-3 sm:mt-4 mx-2"

            initial={{
              scale: 0.95,
            }}

            animate={{
              scale: isMobileMenuOpen ? 1 : 0.95,
            }}

            transition={{
              duration: 0.3,
            }}
          >

            <div className="absolute inset-0 bg-black/95 backdrop-blur-xl rounded-xl sm:rounded-2xl border border-white/10 shadow-2xl overflow-hidden">

              <div className="absolute top-0 -left-8 sm:-left-10 w-24 sm:w-32 h-12 sm:h-16 bg-gradient-to-r from-purple-600/20 to-pink-600/15 rounded-full blur-xl opacity-50" />

              <div className="absolute bottom-0 -right-8 sm:-right-10 w-24 sm:w-32 h-12 sm:h-16 bg-gradient-to-l from-pink-600/20 to-purple-600/15 rounded-full blur-xl opacity-50" />

            </div>


            <div
              className="relative z-10 px-4 sm:px-6 py-3 sm:py-4 space-y-1 sm:space-y-2"
              style={TIMES_FONT}
            >

              {NAVIGATION.map((item, index) => (
                <motion.button
                  key={item.name}

                  initial={{
                    opacity: 0,
                    x: -20,
                  }}

                  animate={{
                    opacity: isMobileMenuOpen ? 1 : 0,
                    x: isMobileMenuOpen ? 0 : -20,
                  }}

                  transition={{
                    duration: 0.3,
                    delay: index * 0.1,
                  }}

                  whileHover={{
                    scale: 1.02,
                    x: 5,
                  }}

                  whileTap={{
                    scale: 0.98,
                  }}

                  onClick={() => scrollToSection(item.href)}

                  className="block w-full text-left px-3 sm:px-4 py-2.5 sm:py-3 text-sm sm:text-base text-gray-300 hover:text-white hover:bg-gradient-to-r hover:from-purple-600/20 hover:to-pink-600/20 rounded-lg sm:rounded-xl transition-all duration-300 font-medium relative group"
                >

                  <span className="relative z-10">
                    {item.name}
                  </span>

                  <motion.div
                    className="absolute inset-0 bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-lg sm:rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300"

                    whileHover={{
                      scale: 1.02,
                    }}
                  />

                </motion.button>
              ))}


              {/* MOBILE FOOTER WORDMARK */}

              <motion.div
                className="pt-3 sm:pt-4 mt-3 sm:mt-4 border-t border-white/10"

                initial={{
                  opacity: 0,
                }}

                animate={{
                  opacity: isMobileMenuOpen ? 1 : 0,
                }}

                transition={{
                  duration: 0.3,
                  delay: 0.4,
                }}
              >

                <p className="text-center text-gray-400 text-xs sm:text-sm">

                  <span
                    style={TIMES_FONT}
                    className="bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent font-medium"
                  >
                    vehnicate
                  </span>

                </p>

              </motion.div>

            </div>

          </motion.div>

        </motion.div>

      </nav>

    </motion.header>
  )
}

export default Header