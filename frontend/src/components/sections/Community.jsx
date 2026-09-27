import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { Users, MessageCircle, Calendar, Award, Star, Globe, ChevronRight, Play } from 'lucide-react'

const Community = () => {
  const [activeTab, setActiveTab] = useState('features')
  
  const communityFeatures = [
    {
      icon: <Users className="w-4 h-4 sm:w-5 sm:h-5 lg:w-6 lg:h-6" />,
      title: "Driver Network",
      description: "Connect with 10,000+ drivers worldwide and share experiences",
      stats: "10k+ Members"
    },
    {
      icon: <MessageCircle className="w-4 h-4 sm:w-5 sm:h-5 lg:w-6 lg:h-6" />,
      title: "Discussion Forums",
      description: "Join 500+ active discussions about driving tips and rewards",
      stats: "500+ Discussions"
    },
    {
      icon: <Calendar className="w-4 h-4 sm:w-5 sm:h-5 lg:w-6 lg:h-6" />,
      title: "Events & Meetups", 
      description: "Attend local driving events and community workshops",
      stats: "50+ Events Monthly"
    },
    {
      icon: <Award className="w-4 h-4 sm:w-5 sm:h-5 lg:w-6 lg:h-6" />,
      title: "Leaderboards",
      description: "Compete globally and showcase your achievements",
      stats: "Weekly Competitions"
    },
    {
      icon: <Star className="w-4 h-4 sm:w-5 sm:h-5 lg:w-6 lg:h-6" />,
      title: "Expert Reviews",
      description: "Get insights from professional driving instructors",
      stats: "100+ Experts"
    },
    {
      icon: <Globe className="w-4 h-4 sm:w-5 sm:h-5 lg:w-6 lg:h-6" />,
      title: "Global Challenges",
      description: "Participate in worldwide driving challenges",
      stats: "Monthly Challenges"
    }
  ]

  const communityStats = [
    {
      icon: <Users className="w-4 h-4 sm:w-5 sm:h-5" />,
      value: "15,000+",
      label: "Active Members"
    },
    {
      icon: <MessageCircle className="w-4 h-4 sm:w-5 sm:h-5" />,
      value: "2.5M+",
      label: "Messages Shared"
    },
    {
      icon: <Award className="w-4 h-4 sm:w-5 sm:h-5" />,
      value: "50K+",
      label: "Badges Earned"
    },
    {
      icon: <Calendar className="w-4 h-4 sm:w-5 sm:h-5" />,
      value: "200+",
      label: "Events Hosted"
    }
  ]

  return (
    <section id="community" className="py-12 sm:py-16 md:py-20 bg-black relative overflow-hidden">
      {/* GRADIENT CONTINUATION FROM TEAM SECTION */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-black via-purple-900/5 to-purple-900/8"></div>
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-purple-900/3 to-pink-600/5"></div>
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black"></div>
      </div>

      {/* Background Patches - Made responsive */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-40 -left-24 sm:-left-32 lg:-left-48 w-48 h-48 sm:w-72 sm:h-72 lg:w-96 lg:h-96 bg-gradient-to-r from-pink-600/15 to-purple-600/10 rounded-full blur-3xl opacity-80" />
        <div className="absolute bottom-40 -right-24 sm:-right-32 lg:-right-48 w-40 h-40 sm:w-60 sm:h-60 lg:w-80 lg:h-80 bg-gradient-to-l from-purple-600/15 to-pink-600/10 rounded-full blur-3xl opacity-80" />
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Header - Made responsive */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          viewport={{ once: true }}
          className="text-center mb-12 sm:mb-16"
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl lg:text-6xl xl:text-7xl 2xl:text-8xl font-ledger font-bold mb-4 sm:mb-6 text-white leading-tight">
            Join Our <span className="bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">Community</span>
          </h2>
          <p className="text-base sm:text-lg md:text-xl text-gray-300 max-w-3xl mx-auto leading-relaxed px-4 sm:px-0">
            Connect with thousands of drivers worldwide in our growing community platform
          </p>
        </motion.div>

        {/* Tab Navigation - Made responsive */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          viewport={{ once: true }}
          className="flex justify-center mb-8 sm:mb-12"
        >
          <div className="inline-flex bg-gray-800/50 backdrop-blur-sm rounded-xl sm:rounded-2xl p-0.5 sm:p-1 border border-gray-700/50">
            <button
              onClick={() => setActiveTab('features')}
              className={`px-3 sm:px-4 lg:px-6 py-2 sm:py-3 rounded-lg sm:rounded-xl font-medium text-sm sm:text-base transition-all duration-300 ${
                activeTab === 'features'
                  ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-lg'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              Features
            </button>
            <button
              onClick={() => setActiveTab('stats')}
              className={`px-3 sm:px-4 lg:px-6 py-2 sm:py-3 rounded-lg sm:rounded-xl font-medium text-sm sm:text-base transition-all duration-300 ${
                activeTab === 'stats'
                  ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-lg'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              Statistics
            </button>
          </div>
        </motion.div>

        {/* Features Tab - Responsive Infinite Horizontal Scroll */}
        {activeTab === 'features' && (
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="relative overflow-hidden mb-12 sm:mb-16"
          >
            {/* Infinite Scrolling Container */}
            <div className="relative">
              <div 
                className="flex gap-3 sm:gap-4 lg:gap-6 animate-scroll"
                style={{
                  width: 'calc(280px * 12)', // Responsive width
                  animation: 'infiniteScroll 30s linear infinite'
                }}
              >
                {/* First set of features */}
                {communityFeatures.map((feature, index) => (
                  <div
                    key={`first-${index}`}
                    className="flex-shrink-0 w-64 sm:w-72 lg:w-80 group"
                  >
                    <div className="glass-card h-full p-4 sm:p-6 border border-white/10 group-hover:border-purple-500/30 transition-all duration-300">
                      <div className="w-8 h-8 sm:w-10 sm:h-10 lg:w-12 lg:h-12 bg-gradient-to-br from-purple-600/20 to-pink-600/20 rounded-lg sm:rounded-xl flex items-center justify-center mb-3 sm:mb-4 group-hover:scale-110 transition-transform duration-300">
                        <div className="text-purple-400">
                          {feature.icon}
                        </div>
                      </div>

                      <h4 className="text-base sm:text-lg font-bold text-white mb-2 sm:mb-3 group-hover:text-purple-300 transition-colors leading-tight">
                        {feature.title}
                      </h4>
                      <p className="text-gray-400 text-xs sm:text-sm leading-relaxed mb-3 sm:mb-4 group-hover:text-gray-300 transition-colors">
                        {feature.description}
                      </p>
                      
                      <div className="inline-flex items-center px-2 sm:px-3 py-1 bg-gradient-to-r from-purple-600/20 to-pink-600/20 rounded-full text-xs font-medium text-purple-300">
                        <Star className="w-2.5 h-2.5 sm:w-3 sm:h-3 mr-1" />
                        {feature.stats}
                      </div>
                    </div>
                  </div>
                ))}
                
                {/* Duplicate set for seamless loop */}
                {communityFeatures.map((feature, index) => (
                  <div
                    key={`second-${index}`}
                    className="flex-shrink-0 w-64 sm:w-72 lg:w-80 group"
                  >
                    <div className="glass-card h-full p-4 sm:p-6 border border-white/10 group-hover:border-purple-500/30 transition-all duration-300">
                      <div className="w-8 h-8 sm:w-10 sm:h-10 lg:w-12 lg:h-12 bg-gradient-to-br from-purple-600/20 to-pink-600/20 rounded-lg sm:rounded-xl flex items-center justify-center mb-3 sm:mb-4 group-hover:scale-110 transition-transform duration-300">
                        <div className="text-purple-400">
                          {feature.icon}
                        </div>
                      </div>

                      <h4 className="text-base sm:text-lg font-bold text-white mb-2 sm:mb-3 group-hover:text-purple-300 transition-colors leading-tight">
                        {feature.title}
                      </h4>
                      <p className="text-gray-400 text-xs sm:text-sm leading-relaxed mb-3 sm:mb-4 group-hover:text-gray-300 transition-colors">
                        {feature.description}
                      </p>
                      
                      <div className="inline-flex items-center px-2 sm:px-3 py-1 bg-gradient-to-r from-purple-600/20 to-pink-600/20 rounded-full text-xs font-medium text-purple-300">
                        <Star className="w-2.5 h-2.5 sm:w-3 sm:h-3 mr-1" />
                        {feature.stats}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}

        {/* Stats Tab - Made responsive */}
        {activeTab === 'stats' && (
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6 mb-12 sm:mb-16"
          >
            {communityStats.map((stat, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, scale: 0.8 }}
                whileInView={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.6, delay: index * 0.1, type: "spring" }}
                viewport={{ once: true }}
                className="glass-card p-4 sm:p-6 text-center border border-white/10 hover:border-purple-500/30 transition-all duration-300 group"
              >
                <motion.div
                  whileHover={{ scale: 1.1 }}
                  transition={{ duration: 0.3 }}
                  className="w-8 h-8 sm:w-10 sm:h-10 bg-gradient-to-r from-purple-600/20 to-pink-600/20 rounded-lg sm:rounded-xl flex items-center justify-center mx-auto mb-3 sm:mb-4"
                >
                  <div className="text-purple-400">
                    {stat.icon}
                  </div>
                </motion.div>
                <div className="text-xl sm:text-2xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent mb-1 sm:mb-2">
                  {stat.value}
                </div>
                <div className="text-gray-400 text-xs sm:text-sm">{stat.label}</div>
              </motion.div>
            ))}
          </motion.div>
        )}

        {/* CTA Section - Made responsive */}
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          whileInView={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          viewport={{ once: true }}
          className="text-center"
        >
          <div className="glass-card font-ledger max-w-3xl mx-auto p-6 sm:p-8 border border-white/10 relative overflow-hidden">
            <div className="relative z-10">
              <h3 className="text-xl sm:text-2xl md:text-3xl font-bold text-white mb-3 sm:mb-4 leading-tight">
                Ready to Join the Community?
              </h3>
              <p className="text-gray-300 text-sm sm:text-base mb-4 sm:mb-6 max-w-xl mx-auto leading-relaxed">
                Be among the first to experience our community platform when it launches.
              </p>
              
              <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 justify-center items-center">
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => {
                    const contact = document.querySelector('#contact')
                    if (!contact) return
                    if (window.__lenis) {
                      window.__lenis.scrollTo(contact, { offset: 0, duration: 1.4 })
                    } else {
                      contact.scrollIntoView({ behavior: 'smooth', block: 'start' })
                    }
                  }}
                  className="w-full sm:w-auto px-4 sm:px-6 py-2.5 sm:py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold text-sm sm:text-base rounded-lg sm:rounded-xl shadow-lg hover:shadow-2xl transition-all duration-300 flex items-center justify-center group"
                >
                  Contact Us
                  <ChevronRight className="ml-2 group-hover:translate-x-1 transition-transform" size={16} />
                </motion.button>
                
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className="w-full sm:w-auto px-4 sm:px-6 py-2.5 sm:py-3 bg-white/10 backdrop-blur-sm border border-white/20 text-white font-semibold text-sm sm:text-base rounded-lg sm:rounded-xl hover:bg-white/20 transition-all duration-300 flex items-center justify-center group"
                >
                  <Play className="mr-2 group-hover:scale-110 transition-transform" size={16} />
                  Preview
                </motion.button>
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* CSS for Infinite Scroll Animation */}
      <style jsx>{`
        @keyframes infiniteScroll {
          from {
            transform: translateX(0);
          }
          to {
            transform: translateX(-50%);
          }
        }
        
        .animate-scroll:hover {
          animation-play-state: paused;
        }
      `}</style>
    </section>
  )
}

export default Community
