Module ModConnection

    Public cn As New ADODB.Connection()

    Public Sub Connect()
        cn.Open("Provider=OraOLEDB.ORACLE;User Id=lp;PAssword=YOUR_ORACLE_PASSWORD;Data Source=orcl")
    End Sub

End Module
