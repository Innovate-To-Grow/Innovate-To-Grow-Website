import {getPagerItems} from './pagerItems';

interface ProjectGridPagerProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  label?: string;
}

/**
 * The reference's DataTables pager, right-aligned under the table: Previous / page numbers / Next on wide screens;
 * Previous / "Page x of y" / Next on phones.
 */
export const ProjectGridPager = ({page, totalPages, onPageChange, label = 'Pages'}: ProjectGridPagerProps) => (
  <nav className="itg-pagination project-grid-pagination" aria-label={label}>
    <button
      type="button"
      className="itg-pagination-link project-grid-pager-step"
      onClick={() => onPageChange(page - 1)}
      disabled={page === 0}
    >
      Previous
    </button>
    <ul className="project-grid-pager-pages">
      {getPagerItems(page, totalPages).map((item) =>
        typeof item === 'number' ? (
          <li key={item}>
            <button
              type="button"
              className="itg-pagination-link project-grid-pager-page"
              aria-label={`Page ${item + 1}`}
              aria-current={item === page ? 'page' : undefined}
              onClick={() => {
                if (item !== page) onPageChange(item);
              }}
            >
              {item + 1}
            </button>
          </li>
        ) : (
          <li key={item} className="itg-pagination-gap" aria-hidden="true">
            …
          </li>
        ),
      )}
    </ul>
    <span className="project-grid-pager-status">
      Page {page + 1} of {totalPages}
    </span>
    <button
      type="button"
      className="itg-pagination-link project-grid-pager-step"
      onClick={() => onPageChange(page + 1)}
      disabled={page >= totalPages - 1}
    >
      Next
    </button>
  </nav>
);
