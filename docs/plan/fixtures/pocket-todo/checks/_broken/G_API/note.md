Removes the Origin check on writes: the CSRF hole the 9 Nov solution shipped with (R6, A2).
G_API must refuse a write from `Origin: http://evil.example` with 403 and fails here.
