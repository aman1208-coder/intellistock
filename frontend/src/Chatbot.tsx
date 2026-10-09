import { AnimatePresence, motion } from 'framer-motion';
import { useState } from 'react';
import { askChatbot, type ChatbotResponse, type Product } from './api';

type ChatRole = 'assistant' | 'user';

type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
};

const previewSuggestions = [
  'Show me zero-stock items',
  'List threshold warnings',
  'Check warehouse capacity',
  'What is pending reorder activity?',
];

export default function Chatbot({ products }: { products?: Product[] }) {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: 'Ask about zero-stock products, reorder thresholds, warehouse capacity, or pending reorders.',
    },
  ]);

  const submitQuestion = async (questionOverride?: string) => {
    const question = (questionOverride ?? input).trim();
    if (!question) {
      return;
    }

    setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'user', text: question }]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await askChatbot(question);
      const answer = response.answer || 'I could not find a relevant answer in the live inventory state.';
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', text: answer }]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          text:
            error instanceof Error
              ? `The assistant is offline: ${error.message}`
              : 'The assistant is offline right now.',
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <motion.button
        type="button"
        className="chat-toggle"
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        onClick={() => setIsOpen((current) => !current)}
      >
        {isOpen ? 'Hide assistant' : 'Open assistant'}
      </motion.button>

      <AnimatePresence>
        {isOpen && (
          <motion.aside
            className="chat-drawer glass-panel"
            initial={{ opacity: 0, y: 32, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.96 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="chat-header">
              <div>
                <span className="eyebrow">AI assistant</span>
                <h3>Inventory copilot</h3>
              </div>
            </div>

            <div className="chat-suggestions">
              {previewSuggestions.map((suggestion) => (
                <button key={suggestion} type="button" className="chip" onClick={() => void submitQuestion(suggestion)}>
                  {suggestion}
                </button>
              ))}
            </div>

            <div className="chat-messages">
              {messages.map((message) => (
                <div key={message.id} className={`chat-bubble ${message.role}`}>
                  {message.text}
                </div>
              ))}
              {isLoading && <div className="chat-bubble assistant">Checking live inventory state...</div>}
            </div>

            <div className="chat-input-row">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    void submitQuestion();
                  }
                }}
                placeholder="Ask about stock levels..."
              />
              <button type="button" className="primary" onClick={() => void submitQuestion()}>
                Send
              </button>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}
