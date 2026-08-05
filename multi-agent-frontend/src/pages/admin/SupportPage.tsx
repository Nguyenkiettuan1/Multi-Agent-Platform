import { MaterialIcon } from '../../components/ui/MaterialIcon'

const faqs = [
  {
    q: 'How do I add a new data source for an agent?',
    a: "To add a new data source, go to the 'Knowledge' tab in the sidebar. Click 'Add Source', choose the data type (PDF, URL, Text), and follow the on-screen instructions.",
  },
  {
    q: 'Why does the agent respond with incorrect information even after I uploaded documents?',
    a: "Check the 'Audit' tab for retrieval logs. The documents may be poorly chunked, or the configured prompt may not be strict enough.",
  },
  {
    q: 'How do I restrict user access to specific agents?',
    a: "Manage access under 'Models' -> 'Access Control'. There you can assign specific agents to user groups based on ID or role.",
  },
]

export function SupportPage() {
  return (
    <div className="p-margin-page">
      <header className="mb-10">
        <h1 className="mb-2 text-display-lg text-primary">Help &amp; Support</h1>
        <p className="max-w-2xl text-body-lg text-on-surface-variant">
          Find answers to common issues or send a support request directly to the engineering team.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="space-y-8 lg:col-span-2">
          <div className="relative">
            <MaterialIcon name="search" className="absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant" />
            <input
              type="text"
              placeholder="Search docs, errors, or questions..."
              className="w-full rounded-xl border border-border-subtle bg-surface py-4 pr-4 pl-12 text-body-md text-on-surface shadow-sm transition-all placeholder:text-on-surface-variant focus:border-transparent focus:ring-2 focus:ring-secondary focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {[
              { icon: 'menu_book', title: 'Admin Documentation', desc: 'Detailed guides for configuring and managing agents.' },
              { icon: 'api', title: 'API Integration', desc: 'Technical documentation for integrating agents into your system.' },
            ].map((card) => (
              <a
                key={card.title}
                href="#"
                className="group flex flex-col items-start gap-4 rounded-xl border border-border-subtle bg-surface p-6 transition-all hover:border-secondary hover:shadow-md"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-container-high text-primary transition-colors group-hover:bg-secondary-container group-hover:text-on-secondary-container">
                  <MaterialIcon name={card.icon} />
                </div>
                <div>
                  <h3 className="mb-1 text-headline-sm text-primary">{card.title}</h3>
                  <p className="text-body-md text-on-surface-variant">{card.desc}</p>
                </div>
              </a>
            ))}
          </div>

          <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface">
            <div className="border-b border-border-subtle p-6">
              <h2 className="flex items-center gap-2 text-headline-sm text-primary">
                <MaterialIcon name="forum" className="text-secondary" />
                Frequently Asked Questions (FAQ)
              </h2>
            </div>
            <div className="divide-y divide-border-subtle">
              {faqs.map((faq) => (
                <details key={faq.q} className="group">
                  <summary className="flex cursor-pointer list-none items-center justify-between p-6 text-label-md text-primary hover:bg-surface-container-low">
                    {faq.q}
                    <MaterialIcon name="expand_more" className="transition-transform group-open:rotate-180" />
                  </summary>
                  <div className="p-6 pt-0 text-body-md text-on-surface-variant">{faq.a}</div>
                </details>
              ))}
            </div>
          </div>
        </div>

        <div className="lg:col-span-1">
          <div className="sticky top-6 rounded-xl border border-border-subtle bg-surface p-6">
            <h2 className="mb-6 flex items-center gap-2 text-headline-sm text-primary">
              <MaterialIcon name="support_agent" className="text-secondary" />
              Submit support request
            </h2>
            <form className="space-y-4">
              <div>
                <label className="mb-1 block text-label-sm text-on-surface-variant">Issue type</label>
                <select className="w-full rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-md text-on-surface focus:border-transparent focus:ring-2 focus:ring-secondary focus:outline-none">
                  <option>System bug</option>
                  <option>Agent configuration</option>
                  <option>Billing &amp; invoices</option>
                  <option>Other</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-label-sm text-on-surface-variant">Priority</label>
                <div className="mt-2 flex gap-4">
                  <label className="flex cursor-pointer items-center gap-2">
                    <input type="radio" name="priority" defaultChecked className="text-secondary focus:ring-secondary" />
                    <span className="text-body-md text-on-surface">Normal</span>
                  </label>
                  <label className="flex cursor-pointer items-center gap-2">
                    <input type="radio" name="priority" className="text-error focus:ring-error" />
                    <span className="text-body-md text-on-surface">Urgent</span>
                  </label>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-label-sm text-on-surface-variant">Details</label>
                <textarea
                  rows={4}
                  placeholder="Describe the issue or your question..."
                  className="w-full resize-none rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-md text-on-surface focus:border-transparent focus:ring-2 focus:ring-secondary focus:outline-none"
                />
                <div className="mt-1 text-right text-label-sm text-on-surface-variant">0/500</div>
              </div>
              <button
                type="button"
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-label-md text-on-primary hover:bg-inverse-surface"
              >
                Submit request
                <MaterialIcon name="send" size={18} />
              </button>
            </form>
            <div className="mt-6 border-t border-border-subtle pt-6">
              <p className="text-center text-label-sm text-on-surface-variant">
                Expected response time: <strong className="text-on-surface">2–4 business hours</strong>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
