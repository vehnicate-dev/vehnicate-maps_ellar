import React, { useState } from "react";
import { motion } from "framer-motion";
import { Mail, Phone, Send, CheckCircle, Linkedin, AlertCircle } from "lucide-react";
import emailjs from '@emailjs/browser';

// Fixed Card component with proper z-index
const Card = ({ children, className = '' }) => (
  <div className={`relative rounded-xl sm:rounded-2xl border border-white/10 backdrop-blur-md bg-white/5 shadow-lg shadow-purple-500/5 ${className}`}>
    {/* Animated gradient border - moved behind content */}
    <div className="absolute inset-0 rounded-xl sm:rounded-2xl border-2 border-transparent group-hover:border-purple-500/40 transition-all duration-500 -z-10"></div>
    {/* Subtle light streak - moved behind content */}
    <div className="absolute -top-20 -left-20 w-40 h-40 bg-gradient-to-br from-purple-400/10 to-pink-400/10 rounded-full blur-2xl group-hover:scale-150 transition-transform duration-700 -z-10"></div>
    <div className="relative z-10">
      {children}
    </div>
  </div>
);

const Contact = () => {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    subject: "",
    message: "",
  });
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  // Your EmailJS config
  const EMAILJS_CONFIG = {
    serviceId: 'service_3v3d3sz',
    adminTemplateId: 'template_7mdmioc',
    replyTemplateId: 'template_ccysqje',
    publicKey: 'XKRZgZZpyV7zxyZNe'
  };

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    if (error) setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    try {
      const templateParams = {
        from_name: formData.name,
        from_email: formData.email,
        subject: formData.subject,
        message: formData.message,
      };

      await emailjs.send(
        EMAILJS_CONFIG.serviceId,
        EMAILJS_CONFIG.adminTemplateId,
        templateParams,
        EMAILJS_CONFIG.publicKey
      );

      await emailjs.send(
        EMAILJS_CONFIG.serviceId,
        EMAILJS_CONFIG.replyTemplateId,
        templateParams,
        EMAILJS_CONFIG.publicKey
      );

      console.log('Both emails sent successfully!');
      setIsSubmitted(true);
      
      setTimeout(() => {
        setIsSubmitted(false);
        setFormData({ name: "", email: "", subject: "", message: "" });
      }, 4000);

    } catch (error) {
      console.error('EmailJS Error:', error);
      setError('Failed to send message. Please try again or contact us directly.');
    } finally {
      setIsLoading(false);
    }
  };

  const contactInfo = [
    {
      icon: <Mail className="w-5 h-5 sm:w-6 sm:h-6 lg:w-8 lg:h-8" />,
      title: "Email Us",
      details: "vehnicate.web@gmail.com",
      action: "mailto:vehnicate.web@gmail.com",
    },
    {
      icon: <Phone className="w-5 h-5 sm:w-6 sm:h-6 lg:w-8 lg:h-8" />,
      title: "Call Us",
      details: "+91 77081 61551",
      action: "tel:+917708161551",
    },
    {
      icon: <Linkedin className="w-5 h-5 sm:w-6 sm:h-6 lg:w-8 lg:h-8" />,
      title: "Connect via LinkedIn",
      details: "",
      action: "https://www.linkedin.com/company/vehnicate/",
    },
  ];

  return (
    <section id="contact" className="py-12 sm:py-16 md:py-20 bg-black relative overflow-hidden">
      {/* Background elements with proper z-index */}
      <div className="absolute inset-0 -z-20">
        <div className="absolute inset-0 bg-gradient-to-b from-black via-purple-900/5 to-purple-900/10"></div>
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-purple-900/3 to-pink-600/8"></div>
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black"></div>
      </div>

      <div className="absolute inset-0 overflow-hidden pointer-events-none -z-10">
        <div className="absolute top-32 left-1/2 -translate-x-1/2 w-80 h-64 sm:w-96 sm:h-80 lg:w-[600px] lg:h-[400px] bg-gradient-to-b from-purple-600/25 to-pink-600/15 rounded-full blur-3xl opacity-60" />
        <div className="absolute bottom-0 -left-20 sm:-left-32 lg:-left-40 w-64 h-64 sm:w-80 sm:h-80 lg:w-[500px] lg:h-[500px] bg-gradient-to-r from-pink-600/20 to-purple-600/15 rounded-full blur-3xl opacity-70" />
        <div className="absolute bottom-0 -right-20 sm:-right-32 lg:-right-40 w-56 h-56 sm:w-72 sm:h-72 lg:w-[400px] lg:h-[400px] bg-gradient-to-l from-purple-600/20 to-pink-600/15 rounded-full blur-3xl opacity-70" />
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          viewport={{ once: true }}
          className="text-center mb-12 sm:mb-16"
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl lg:text-6xl xl:text-7xl 2xl:text-8xl font-ledger font-bold mb-4 sm:mb-6 text-white leading-tight">
            Get In{" "}
            <span className="bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">
              Touch
            </span>
          </h2>
          <p className="text-base sm:text-lg md:text-xl lg:text-2xl text-gray-300 leading-relaxed font-ledger max-w-4xl mx-auto px-4 sm:px-0">
            Have questions about vehnicate? Want to partner with us? <br className="hidden sm:block" />
            <span className="bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent font-semibold">
              We'd love to hear from you!
            </span>
          </p>
        </motion.div>

        <div className="font-ledger grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12">
          {/* Contact Information */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8 }}
            viewport={{ once: true }}
          >
            <h3 className="text-lg sm:text-xl lg:text-2xl font-bold font-ledger text-white mb-6 sm:mb-8">
              Contact Information
            </h3>
            <div className="space-y-6 sm:space-y-8">
              {contactInfo.map((info, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.6, delay: index * 0.1 }}
                  viewport={{ once: true }}
                  className="group"
                >
                  <a href={info.action} className="block">
                    <Card className="group hover:scale-[1.03] transition-transform duration-500">
                      <div className="relative p-4 sm:p-6">
                        <div className="absolute -top-4 sm:-top-6 left-4 sm:left-6 w-12 h-12 sm:w-14 sm:h-14 lg:w-16 lg:h-16 bg-gradient-to-br from-purple-600 to-pink-600 rounded-xl sm:rounded-2xl flex items-center justify-center shadow-xl shadow-purple-500/30 transform group-hover:rotate-6 group-hover:scale-110 transition-all duration-500 z-20">
                          <div className="text-white">{info.icon}</div>
                        </div>

                        <div className="mt-6 sm:mt-8">
                          <h4 className="text-base sm:text-lg font-semibold text-white group-hover:text-purple-300 transition-colors duration-300 leading-tight">
                            {info.title}
                          </h4>
                          {info.details && (
                            <p className="text-sm sm:text-base text-gray-400 group-hover:text-gray-200 transition-colors duration-300 mt-1">
                              {info.details}
                            </p>
                          )}
                        </div>
                      </div>
                    </Card>
                  </a>
                </motion.div>
              ))}
            </div>

            {/* Business Hours */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              viewport={{ once: true }}
              className="mt-8 sm:mt-10 group"
            >
              <Card className="group hover:scale-[1.02] transition-transform duration-500">
                <div className="relative p-4 sm:p-6">
                  <h4 className="text-base sm:text-lg font-semibold text-white mb-2 sm:mb-3 group-hover:text-purple-300 transition-colors duration-300">
                    Business Hours
                  </h4>
                  <div className="text-gray-400 group-hover:text-gray-200 transition-colors duration-300 space-y-1 text-sm sm:text-base">
                    <p>uhm... we dont think the boundaries are well defined</p>
                    <p>mail/message us at anytime</p>
                  </div>
                </div>
              </Card>
            </motion.div>
          </motion.div>

          {/* Contact Form - Fixed version */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8 }}
            viewport={{ once: true }}
            className="group"
          >
            <Card className="group hover:scale-[1.02] transition-transform duration-500">
              <div className="relative p-6 sm:p-8 z-20">
                {!isSubmitted ? (
                  <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-6 relative z-30">
                    {error && (
                      <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="flex items-center space-x-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg relative z-40"
                      >
                        <AlertCircle className="w-5 h-5 text-red-400" />
                        <span className="text-sm text-red-300">{error}</span>
                      </motion.div>
                    )}

                    <div className="relative z-40">
                      <label className="block text-xs sm:text-sm font-medium text-gray-300 mb-2">
                        Name
                      </label>
                      <input
                        type="text"
                        name="name"
                        value={formData.name}
                        onChange={handleChange}
                        required
                        disabled={isLoading}
                        className="w-full px-3 sm:px-4 py-2.5 sm:py-3 bg-white/10 border border-white/20 rounded-lg text-sm sm:text-base text-white placeholder-gray-400 focus:outline-none focus:border-purple-500 focus:bg-white/20 transition-all duration-300 disabled:opacity-50 relative z-50"
                        placeholder="Your Name"
                        style={{ zIndex: 50 }}
                      />
                    </div>

                    <div className="relative z-40">
                      <label className="block text-xs sm:text-sm font-medium text-gray-300 mb-2">
                        Email
                      </label>
                      <input
                        type="email"
                        name="email"
                        value={formData.email}
                        onChange={handleChange}
                        required
                        disabled={isLoading}
                        className="w-full px-3 sm:px-4 py-2.5 sm:py-3 bg-white/10 border border-white/20 rounded-lg text-sm sm:text-base text-white placeholder-gray-400 focus:outline-none focus:border-purple-500 focus:bg-white/20 transition-all duration-300 disabled:opacity-50 relative z-50"
                        placeholder="your@email.com"
                        style={{ zIndex: 50 }}
                      />
                    </div>

                    <div className="relative z-40">
                      <label className="block text-xs sm:text-sm font-medium text-gray-300 mb-2">
                        Subject
                      </label>
                      <input
                        type="text"
                        name="subject"
                        value={formData.subject}
                        onChange={handleChange}
                        required
                        disabled={isLoading}
                        className="w-full px-3 sm:px-4 py-2.5 sm:py-3 bg-white/10 border border-white/20 rounded-lg text-sm sm:text-base text-white placeholder-gray-400 focus:outline-none focus:border-purple-500 focus:bg-white/20 transition-all duration-300 disabled:opacity-50 relative z-50"
                        placeholder="What's this about?"
                        style={{ zIndex: 50 }}
                      />
                    </div>

                    <div className="relative z-40">
                      <label className="block text-xs sm:text-sm font-medium text-gray-300 mb-2">
                        Message
                      </label>
                      <textarea
                        name="message"
                        value={formData.message}
                        onChange={handleChange}
                        required
                        disabled={isLoading}
                        rows={4}
                        className="w-full px-3 sm:px-4 py-2.5 sm:py-3 bg-white/10 border border-white/20 rounded-lg text-sm sm:text-base text-white placeholder-gray-400 focus:outline-none focus:border-purple-500 focus:bg-white/20 transition-all duration-300 resize-none disabled:opacity-50 relative z-50"
                        placeholder="Tell us more..."
                        style={{ zIndex: 50 }}
                      />
                    </div>

                    <motion.button
                      whileHover={{ scale: isLoading ? 1 : 1.02 }}
                      whileTap={{ scale: isLoading ? 1 : 0.98 }}
                      type="submit"
                      disabled={isLoading}
                      className="w-full px-4 sm:px-6 py-2.5 sm:py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold text-sm sm:text-base rounded-lg shadow-lg hover:shadow-2xl transition-all duration-300 flex items-center justify-center group disabled:opacity-70 disabled:cursor-not-allowed relative z-50"
                    >
                      {isLoading ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 sm:h-5 sm:w-5 border-b-2 border-white mr-2"></div>
                          Sending...
                        </>
                      ) : (
                        <>
                          <Send className="mr-2 group-hover:translate-x-1 transition-transform w-4 h-4 sm:w-5 sm:h-5" />
                          Send Message
                        </>
                      )}
                    </motion.button>
                  </form>
                ) : (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="text-center py-6 sm:py-8 relative z-40"
                  >
                    <CheckCircle className="w-12 h-12 sm:w-16 sm:h-16 text-green-400 mx-auto mb-3 sm:mb-4" />
                    <h3 className="text-xl sm:text-2xl font-bold text-white mb-2">
                      Message Sent Successfully!
                    </h3>
                    <p className="text-sm sm:text-base text-gray-300 mb-2">
                      Thank you for reaching out. We'll get back to you within 24 hours!
                    </p>
                    <p className="text-xs text-purple-300">
                      Check your email for a confirmation message.
                    </p>
                  </motion.div>
                )}
              </div>
            </Card>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

export default Contact;
