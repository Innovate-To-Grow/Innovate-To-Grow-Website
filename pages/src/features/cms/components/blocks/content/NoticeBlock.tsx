import { SafeHtml } from '@/components/SafeHtml/SafeHtml';

export type NoticeStyle = 'info' | 'warning' | 'success';

export interface NoticeData {
  heading?: string;
  /** The admin editor offers info, warning and success; anything else renders as info. */
  style?: NoticeStyle;
  body_html: string;
}

const STYLE_CLASSES: Record<NoticeStyle, string> = {
  info: 'itg-notice',
  warning: 'itg-notice itg-notice-warning',
  success: 'itg-notice itg-notice-success',
};

function noticeStyle(value: unknown): NoticeStyle {
  const key = typeof value === 'string' ? value.trim().toLowerCase() : '';
  return Object.hasOwn(STYLE_CLASSES, key) ? (key as NoticeStyle) : 'info';
}

/** Callout box: the global .itg-notice (blue rule), gold for warning, green for success. */
export const NoticeBlock = ({ data }: { data: NoticeData }) => {
  const style = noticeStyle(data.style);
  const heading = typeof data.heading === 'string' ? data.heading.trim() : '';

  return (
    <section className={`cms-notice cms-notice--${style} ${STYLE_CLASSES[style]}`} role="note">
      {heading && <h2 className="cms-notice-title">{heading}</h2>}
      <SafeHtml className="cms-prose cms-notice-body" html={data.body_html ?? ''} />
    </section>
  );
};
