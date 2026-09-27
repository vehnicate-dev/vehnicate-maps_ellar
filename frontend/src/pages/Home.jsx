import React, { useLayoutEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import Header from '../components/common/Header'
import Footer from '../components/common/Footer'
import Hero from '../components/sections/Hero'
import MobileApp from '../components/sections/MobileApp'
import Ellar from '../components/sections/EllarSection'
import Community from '../components/sections/Community'
import Contact from '../components/sections/Contact'
import VMN from '../components/sections/vmn'
import WhyDoIt from '../components/sections/WhyDoIt'
import Maps from '../components/sections/Maps'

const Home = () => {
  const homeRef = useRef(null)
  const location = useLocation()

  useLayoutEffect(() => {
    const sectionId = location.state?.scrollToSection
    if (!sectionId) return

    const timer = window.setTimeout(() => {
      const target = homeRef.current?.querySelector(`[id="${sectionId}"]`)
      if (!target) return

      if (window.__lenis) {
        window.__lenis.scrollTo(target, { offset: 0, duration: 1.4 })
      } else {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }, 450)

    return () => window.clearTimeout(timer)
  }, [location.key, location.state])

  return (
    <div ref={homeRef} className="min-h-screen bg-black text-white">
      <Header />
      <Hero />
      <WhyDoIt/>
      <MobileApp />
      <Ellar />
      <VMN/>
      <Maps />
      <Contact />
      <Footer />
    </div>
  )
}

export default Home
