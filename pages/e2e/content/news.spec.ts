// News list (pagination, empty) + article detail (content, source link, 404).
import {test, expect} from './fixtures';
import {mockNews, newsArticle, newsList} from './helpers';

test('news list renders article cards', {tag: '@core'}, async ({page}) => {
  await mockNews(page, {list: newsList({count: 3})});
  await page.goto('/news', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'News', exact: true})).toBeVisible();
  await expect(page.locator('.news-card').first()).toBeVisible();
});

test('news pagination advances to the next page', async ({page}) => {
  await mockNews(page, {
    listByPage: {1: newsList({count: 18, page: 1}), 2: newsList({count: 18, page: 2})},
  });
  await page.goto('/news', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.news-pagination-info')).toContainText('Page 1 of 2');
  await page.getByRole('button', {name: 'Next'}).click();
  await expect(page.locator('.news-pagination-info')).toContainText('Page 2 of 2');
});

test('news empty state', async ({page}) => {
  await mockNews(page, {list: {count: 0, next: null, previous: null, results: []}});
  await page.goto('/news', {waitUntil: 'domcontentloaded'});
  await expect(page.getByText('No news articles available.')).toBeVisible();
});

test('news detail renders content and source link', {tag: '@core'}, async ({page}) => {
  const article = newsArticle({id: 'news-detail-1', title: 'Detailed Headline', content: '<p>Body paragraph.</p>'});
  await mockNews(page, {detail: article});
  await page.goto('/news/news-detail-1', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Detailed Headline'})).toBeVisible();
  await expect(page.locator('.news-detail-content')).toContainText('Body paragraph.');
  await expect(page.getByRole('link', {name: 'View original article'})).toBeVisible();
});

test('news detail shows not-found on 404', async ({page}) => {
  await mockNews(page, {detailStatus: 404});
  await page.goto('/news/missing-article', {waitUntil: 'domcontentloaded'});
  await expect(page.getByText('Unable to load this article.')).toBeVisible();
});
