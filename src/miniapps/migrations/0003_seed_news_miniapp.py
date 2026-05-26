"""Seed the News MiniApp with code and migrate existing NewsArticle data."""

from django.db import migrations

NEWS_HTML = '<div id="app"></div>'

NEWS_CSS = """\
.loading { text-align: center; padding: 48px; color: #666; }
.news-error { text-align: center; padding: 48px; color: #c62828; }
.news-title { font-size: 2rem; margin-bottom: 24px; color: #0f2d52; }
.news-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 24px; }
.news-card { display: block; text-decoration: none; color: inherit; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.12); transition: box-shadow .2s; cursor: pointer; }
.news-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.15); }
.news-card-img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; background: #e0e0e0; }
.news-card-placeholder { min-height: 180px; }
.news-card-body { padding: 16px; }
.news-card-title { font-size: 1.1rem; margin-bottom: 8px; line-height: 1.3; color: #1a1a1a; }
.news-card-date { font-size: .85rem; color: #666; display: block; margin-bottom: 8px; }
.news-card-summary { font-size: .9rem; color: #444; line-height: 1.5; }
.news-pagination { display: flex; align-items: center; justify-content: center; gap: 16px; margin-top: 32px; padding: 16px 0; }
.news-btn { padding: 8px 20px; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: .9rem; }
.news-btn:hover:not(:disabled) { background: #f5f5f5; }
.news-btn:disabled { opacity: .5; cursor: not-allowed; }
.news-back { display: inline-block; margin-bottom: 16px; color: #1565c0; text-decoration: none; font-size: .9rem; }
.news-back:hover { text-decoration: underline; }
.news-hero { margin-bottom: 24px; }
.news-hero img { width: 100%; max-height: 500px; object-fit: cover; border-radius: 8px; }
.news-hero figcaption { font-size: .85rem; color: #666; margin-top: 8px; font-style: italic; }
.news-detail-title { font-size: 2rem; margin: 16px 0 12px; color: #0f2d52; line-height: 1.3; }
.news-detail-meta { font-size: .9rem; color: #666; margin-bottom: 24px; display: flex; gap: 16px; flex-wrap: wrap; }
.news-author { font-weight: 600; }
.news-content { line-height: 1.8; margin-bottom: 24px; font-size: 1rem; }
.news-content img { max-width: 100%; height: auto; border-radius: 4px; margin: 16px 0; }
.news-content p { margin-bottom: 1em; }
.news-source-link { display: inline-block; margin-top: 16px; color: #1565c0; text-decoration: none; font-size: .9rem; }
.news-source-link:hover { text-decoration: underline; }
"""

NEWS_JS = """\
(function() {
  var app = document.getElementById('app');
  var currentPath = window.__ITG_PATH || '/news';
  var pathParts = currentPath.replace(/\\/$/, '').split('/');
  var articleId = pathParts.length > 2 ? pathParts[2] : null;

  if (articleId) {
    renderDetail(articleId);
  } else {
    renderList(1);
  }

  function renderList(page) {
    app.innerHTML = '<div class="loading">Loading...</div>';
    ITG.api.list({ page: String(page), page_size: '12', ordering: '-published_at' })
      .then(function(data) {
        var totalPages = Math.ceil(data.count / 12);
        var html = '<h1 class="news-title">News</h1><div class="news-grid">';
        data.results.forEach(function(record) {
          var d = record.data;
          var dateStr = formatDate(d.published_at);
          html += '<div class="news-card" data-id="' + record.id + '">';
          if (d.image_url) {
            html += '<img class="news-card-img" src="' + escapeAttr(d.image_url) + '" alt="" loading="lazy">';
          } else {
            html += '<div class="news-card-img news-card-placeholder"></div>';
          }
          html += '<div class="news-card-body">';
          html += '<h2 class="news-card-title">' + escapeHtml(d.title) + '</h2>';
          html += '<time class="news-card-date">' + dateStr + '</time>';
          if (d.summary) html += '<p class="news-card-summary">' + escapeHtml(d.summary) + '</p>';
          html += '</div></div>';
        });
        html += '</div>';
        if (totalPages > 1) {
          html += '<div class="news-pagination">';
          html += '<button class="news-btn" ' + (page <= 1 ? 'disabled' : '') + ' data-page="' + (page - 1) + '">Previous</button>';
          html += '<span>Page ' + page + ' of ' + totalPages + '</span>';
          html += '<button class="news-btn" ' + (page >= totalPages ? 'disabled' : '') + ' data-page="' + (page + 1) + '">Next</button>';
          html += '</div>';
        }
        app.innerHTML = html;
        app.querySelectorAll('.news-card').forEach(function(card) {
          card.addEventListener('click', function() {
            ITG.navigate('/news/' + card.dataset.id);
          });
        });
        app.querySelectorAll('.news-btn:not([disabled])').forEach(function(btn) {
          btn.addEventListener('click', function() {
            renderList(parseInt(btn.dataset.page));
          });
        });
        ITG.resize();
      })
      .catch(function() {
        app.innerHTML = '<div class="news-error">Unable to load news articles.</div>';
        ITG.resize();
      });
  }

  function renderDetail(id) {
    app.innerHTML = '<div class="loading">Loading...</div>';
    ITG.api.get(id)
      .then(function(record) {
        var d = record.data;
        var dateStr = formatDate(d.published_at);
        var html = '<a href="javascript:void(0)" class="news-back">&larr; Back to News</a>';
        if (d.hero_image_url) {
          html += '<figure class="news-hero"><img src="' + escapeAttr(d.hero_image_url) + '" alt="">';
          if (d.hero_caption) html += '<figcaption>' + escapeHtml(d.hero_caption) + '</figcaption>';
          html += '</figure>';
        }
        html += '<h1 class="news-detail-title">' + escapeHtml(d.title) + '</h1>';
        html += '<div class="news-detail-meta">';
        if (d.author) html += '<span class="news-author">' + escapeHtml(d.author) + '</span>';
        html += '<time>' + dateStr + '</time></div>';
        if (d.content) {
          html += '<div class="news-content">' + sanitizeHtml(d.content) + '</div>';
        } else if (d.summary) {
          html += '<p class="news-content">' + escapeHtml(d.summary) + '</p>';
        }
        if (d.source_url) {
          html += '<a href="' + escapeAttr(d.source_url) + '" target="_blank" rel="noopener" class="news-source-link">View original article &rarr;</a>';
        }
        app.innerHTML = html;
        bindBackLink();
        ITG.resize();
      })
      .catch(function() {
        app.innerHTML = '<a href="javascript:void(0)" class="news-back">&larr; Back to News</a><div class="news-error">Article not found.</div>';
        bindBackLink();
        ITG.resize();
      });
  }

  function bindBackLink() {
    var link = app.querySelector('.news-back');
    if (link) {
      link.addEventListener('click', function(e) {
        e.preventDefault();
        ITG.navigate('/news');
      });
    }
  }

  function sanitizeHtml(html) {
    if (!html) return '';
    var div = document.createElement('div');
    div.innerHTML = html;
    var scripts = div.querySelectorAll('script,iframe,object,embed,form');
    for (var i = scripts.length - 1; i >= 0; i--) scripts[i].remove();
    var all = div.querySelectorAll('*');
    for (var j = 0; j < all.length; j++) {
      var attrs = all[j].attributes;
      for (var k = attrs.length - 1; k >= 0; k--) {
        if (attrs[k].name.startsWith('on')) all[j].removeAttribute(attrs[k].name);
      }
      if (all[j].tagName === 'A') {
        var href = all[j].getAttribute('href') || '';
        if (href.match(/^\\s*javascript:/i)) all[j].removeAttribute('href');
      }
    }
    return div.innerHTML;
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  function escapeAttr(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function formatDate(isoStr) {
    if (!isoStr) return '';
    try {
      return new Date(isoStr).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    } catch(e) {
      return isoStr;
    }
  }
})();
"""

NEWS_SCHEMA_FIELDS = [
    {"name": "title", "type": "text", "required": True, "max_length": 500},
    {"name": "source_url", "type": "url", "required": False},
    {"name": "summary", "type": "text", "required": False},
    {"name": "image_url", "type": "url", "required": False},
    {"name": "author", "type": "text", "required": False, "max_length": 255},
    {"name": "published_at", "type": "datetime", "required": True},
    {"name": "content", "type": "text", "required": False},
    {"name": "hero_image_url", "type": "url", "required": False},
    {"name": "hero_caption", "type": "text", "required": False, "max_length": 500},
    {"name": "source", "type": "text", "required": False, "max_length": 100},
    {"name": "source_guid", "type": "text", "required": False, "max_length": 500},
]


def seed_news_miniapp(apps, schema_editor):
    MiniApp = apps.get_model("miniapps", "MiniApp")
    MiniAppDataSchema = apps.get_model("miniapps", "MiniAppDataSchema")
    MiniAppDataRecord = apps.get_model("miniapps", "MiniAppDataRecord")

    app, _ = MiniApp.objects.get_or_create(
        slug="news",
        defaults={
            "url_path": "/news",
            "title": "News",
            "status": "published",
            "embeddable": True,
            "url_prefix_match": True,
            "html_code": NEWS_HTML,
            "js_code": NEWS_JS,
            "css_code": NEWS_CSS,
            "description": "UC Merced news articles synced from RSS feed.",
        },
    )

    MiniAppDataSchema.objects.get_or_create(
        app=app,
        defaults={"fields": NEWS_SCHEMA_FIELDS},
    )

    # Copy existing NewsArticle data if the model still exists
    try:
        NewsArticle = apps.get_model("cms", "NewsArticle")
        if MiniAppDataRecord.objects.filter(app=app).exists():
            return  # Already migrated

        for article in NewsArticle.objects.all().iterator():
            MiniAppDataRecord.objects.create(
                id=article.pk,
                app=app,
                data={
                    "title": article.title or "",
                    "source_url": article.source_url or "",
                    "summary": article.summary or "",
                    "image_url": article.image_url or "",
                    "author": article.author or "",
                    "published_at": article.published_at.isoformat() if article.published_at else "",
                    "content": article.content or "",
                    "hero_image_url": article.hero_image_url or "",
                    "hero_caption": article.hero_caption or "",
                    "source": article.source or "",
                    "source_guid": article.source_guid or "",
                },
            )
    except LookupError:
        pass  # NewsArticle model already removed


def reverse_seed(apps, schema_editor):
    MiniApp = apps.get_model("miniapps", "MiniApp")
    MiniApp.objects.filter(slug="news").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("miniapps", "0002_miniapp_url_prefix_match"),
        ("cms", "0015_cmsembedwidget_schedule"),
    ]

    operations = [
        migrations.RunPython(seed_news_miniapp, reverse_seed),
    ]
