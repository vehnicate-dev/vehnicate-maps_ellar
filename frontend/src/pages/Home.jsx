import React from 'react'
import Header from '../components/common/Header'
import Footer from '../components/common/Footer'
import Hero from '../components/sections/Hero'
import About from '../components/sections/About'
import Working from '../components/sections/Working'
import Community from '../components/sections/Community'
import Contact from '../components/sections/Contact'
import Waitlist from '../components/sections/Waitlist'
import WhyDoIt from '../components/sections/WhyDoIt'

const Home = () => {
  return (
    <div className="min-h-screen bg-black text-white">
      <Header />
      <Hero />
      <WhyDoIt/>
      <About />
      <Working />
      <Waitlist/>
      <Contact />
      <Footer />
    </div>
  )
}

export default Home
