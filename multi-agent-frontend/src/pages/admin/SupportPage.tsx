import { MaterialIcon } from '../../components/ui/MaterialIcon'

const faqs = [
  {
    q: 'Làm thế nào để thêm nguồn dữ liệu mới cho Agent?',
    a: "Để thêm nguồn dữ liệu mới, điều hướng đến tab 'Knowledge' trong Sidebar. Nhấp vào nút 'Add Source', chọn loại dữ liệu (PDF, URL, Text) và làm theo hướng dẫn trên màn hình.",
  },
  {
    q: 'Tại sao Agent phản hồi sai thông tin dù đã cung cấp tài liệu?',
    a: "Vui lòng kiểm tra lại tab 'Audit' để xem nhật ký truy xuất. Có thể tài liệu bị phân mảnh chưa tốt (chunking) hoặc Prompt cấu hình chưa đủ chặt chẽ.",
  },
  {
    q: 'Cách giới hạn quyền truy cập của User vào một số Agent cụ thể?',
    a: "Bạn có thể quản lý quyền truy cập trong phần 'Models' -> 'Access Control'. Tại đây, bạn có thể gán các Agent cụ thể cho các nhóm người dùng dựa trên ID hoặc Role.",
  },
]

export function SupportPage() {
  return (
    <div className="p-margin-page">
      <header className="mb-10">
        <h1 className="mb-2 text-display-lg text-primary">Trợ giúp &amp; Hỗ trợ</h1>
        <p className="max-w-2xl text-body-lg text-on-surface-variant">
          Tìm kiếm câu trả lời cho các vấn đề thường gặp hoặc gửi yêu cầu hỗ trợ trực tiếp đến đội ngũ kỹ thuật.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="space-y-8 lg:col-span-2">
          <div className="relative">
            <MaterialIcon name="search" className="absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant" />
            <input
              type="text"
              placeholder="Tìm kiếm tài liệu, lỗi hoặc câu hỏi..."
              className="w-full rounded-xl border border-border-subtle bg-surface py-4 pr-4 pl-12 text-body-md text-on-surface shadow-sm transition-all placeholder:text-on-surface-variant focus:border-transparent focus:ring-2 focus:ring-secondary focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {[
              { icon: 'menu_book', title: 'Tài liệu Quản trị', desc: 'Hướng dẫn chi tiết cách cấu hình và quản lý Agent.' },
              { icon: 'api', title: 'API Integration', desc: 'Tài liệu kỹ thuật về việc tích hợp Agent vào hệ thống của bạn.' },
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
                Câu hỏi thường gặp (FAQ)
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
              Gửi yêu cầu hỗ trợ
            </h2>
            <form className="space-y-4">
              <div>
                <label className="mb-1 block text-label-sm text-on-surface-variant">Loại vấn đề</label>
                <select className="w-full rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-md text-on-surface focus:border-transparent focus:ring-2 focus:ring-secondary focus:outline-none">
                  <option>Lỗi hệ thống (Bugs)</option>
                  <option>Cấu hình Agent</option>
                  <option>Thanh toán &amp; Hóa đơn</option>
                  <option>Khác</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-label-sm text-on-surface-variant">Mức độ ưu tiên</label>
                <div className="mt-2 flex gap-4">
                  <label className="flex cursor-pointer items-center gap-2">
                    <input type="radio" name="priority" defaultChecked className="text-secondary focus:ring-secondary" />
                    <span className="text-body-md text-on-surface">Bình thường</span>
                  </label>
                  <label className="flex cursor-pointer items-center gap-2">
                    <input type="radio" name="priority" className="text-error focus:ring-error" />
                    <span className="text-body-md text-on-surface">Khẩn cấp</span>
                  </label>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-label-sm text-on-surface-variant">Mô tả chi tiết</label>
                <textarea
                  rows={4}
                  placeholder="Mô tả lỗi hoặc câu hỏi của bạn..."
                  className="w-full resize-none rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-md text-on-surface focus:border-transparent focus:ring-2 focus:ring-secondary focus:outline-none"
                />
                <div className="mt-1 text-right text-label-sm text-on-surface-variant">0/500</div>
              </div>
              <button
                type="button"
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-label-md text-on-primary hover:bg-inverse-surface"
              >
                Gửi yêu cầu
                <MaterialIcon name="send" size={18} />
              </button>
            </form>
            <div className="mt-6 border-t border-border-subtle pt-6">
              <p className="text-center text-label-sm text-on-surface-variant">
                Thời gian phản hồi dự kiến: <strong className="text-on-surface">2-4 giờ làm việc</strong>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
