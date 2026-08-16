# Parser hotfix

This build fixes a Racing & Sports markdown parsing bug where barrier/BP numbers could be mistaken for runner numbers. When that happened, the following jockey name could be displayed as the horse.

The mobile app now:
- anchors runner detection on the actual race-field header;
- accepts only standalone bold runner numbers (`**1**`, `**2**`, etc.);
- requires a `/thoroughbred/horse/` hyperlink inside each runner block;
- passes raw markdown to the existing runner parser so horse, jockey and trainer links cannot be confused;
- ignores the standalone race number at the top of the page.

Verified against the supplied Prix Minerve race: 1 CALASITA, 2 VENETIA, 3 HABIBI, 4 HATANKA FAL, 5 ROMANTIC SYMPHONY, 6 DISPATCHES, 7 PROXIMA DU CENTAUR.
