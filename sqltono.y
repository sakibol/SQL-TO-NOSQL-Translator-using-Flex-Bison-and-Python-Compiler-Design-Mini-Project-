%{

    
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>
    
    // Function 
    int yylex();
    void yyerror(const char *s);
%}

%union {
    char* strval;
}

%token SELECT FROM WHERE AND STAR EQUALS LESS LESS_E GREAT GREAT_E COMMA SEMICOLON
%token <strval> IDENTIFIER NUMBER STRING_LITERAL

%left AND OR

%type <strval> value
%type <strval> condition
%type <strval> column_list

%%

// The Main Entry Point 
query:
    select_stmt SEMICOLON { printf("\nTranslation Successful!\n"); }
    ;

// Grammar Rules 
select_stmt:
    SELECT STAR FROM IDENTIFIER 
    {
        // $4 is table name 

        printf("MongoDB Query: db.%s.find({ });", $4);
        
    }

    | SELECT STAR FROM IDENTIFIER WHERE condition 
    {
          //$6 is string from condition

        printf("MongoDB Query: db.%s.find({ %s });", $4, $6);
	    free($6); 
    }

    | SELECT column_list FROM IDENTIFIER 
    {
        printf("MongoDB Query: db.%s.find({ }, { %s });", $4, $2);
        free($2);
    }

    | SELECT column_list FROM IDENTIFIER WHERE condition 
    {
        printf("MongoDB Query: db.%s.find({ %s }, { %s });", $4, $6, $2);
        free($6); 
        free($2);
    }
    ;

condition:
    IDENTIFIER EQUALS value 
    {
        
        {
    	size_t len = strlen($1) + strlen($3) + 30;  
    	$$ = malloc(len);

    	if ($$ == NULL) { fprintf(stderr, "Out of memory\n");exit(1); }  // Error handeling

    	sprintf($$, "\"%s\": %s", $1, $3);
	} 
    }

    | IDENTIFIER LESS value
    {	
	size_t len = strlen($1) + strlen($3) + 30; 
	$$ = malloc(len);
	if ($$ == NULL) { fprintf(stderr, "Out of memory\n");exit(1); }

	sprintf($$, "\"%s\": { \"$lt\": %s }", $1, $3); 
    }

    | IDENTIFIER LESS_E value
    {
	size_t len = strlen($1) + strlen($3) + 30; 
	$$ = malloc(len);
	if ($$ == NULL) { fprintf(stderr, "Out of memory\n"); exit(1); }

	sprintf($$, "\"%s\": { \"$lte\": %s }", $1, $3); 
    }
    
    | IDENTIFIER GREAT_E value
    {
	size_t len = strlen($1) + strlen($3) + 30; 
	$$ = malloc(len);
    if ($$ == NULL) { fprintf(stderr, "Out of memory\n"); exit(1); }

	sprintf($$, "\"%s\": { \"$gte\": %s }", $1, $3); 
    }

    | IDENTIFIER GREAT value
    {
    size_t len = strlen($1) + strlen($3) + 30;
	$$ = malloc(len);
    if ($$ == NULL) { fprintf(stderr, "Out of memory\n");exit(1); }
	
	sprintf($$, "\"%s\": { \"$gt\": %s }", $1, $3); 
    }

    | condition AND condition 
    {
    size_t len = strlen($1) + strlen($3) + 30;
	$$ = malloc(len);
	
	if ($$ == NULL) { fprintf(stderr, "Out of memory\n");exit(1); }
	
	sprintf($$, "%s, %s", $1,$3);
	free($1); free($3);	
    }

    | condition OR condition 
    {
    size_t len = strlen($1) + strlen($3) + 30;
	$$ = malloc(len);
	
	if ($$ == NULL) { fprintf(stderr, "Out of memory\n");exit(1); }
	
	sprintf($$, "$or: [ {%s}, {%s} ]", $1, $3);
	free($1); free($3);
    }
    ;

value:
    NUMBER          { $$ = $1; }
    | STRING_LITERAL { $$ = $1; }
    // | if we want to add nested loop
    ;

column_list:
    IDENTIFIER
    {
        size_t len = strlen($1) + 30;
        $$ = malloc(len);
        if ($$ == NULL) { fprintf(stderr, "Out of memory\n"); exit(1); }
        sprintf($$, "\"%s\": 1", $1);
    }
    | column_list COMMA IDENTIFIER
    {
        size_t len = strlen($1) + strlen($3) + 20;
        $$ = malloc(len);
        if ($$ == NULL) { fprintf(stderr, "Out of memory\n"); exit(1); }
        
        sprintf($$, "%s, \"%s\": 1", $1, $3);
        free($1); 
    }
    ;

%%

void yyerror(const char *s) {
    fprintf(stderr, "Parse Error: %s\n", s);
}

int main() {
    printf("Enter SQL Query (e.g., SELECT * FROM users WHERE id = 5;):\n> ");
    yyparse();
    return 0;
}